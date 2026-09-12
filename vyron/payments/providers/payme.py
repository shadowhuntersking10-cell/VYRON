"""Payme adapter (Uzbekistan) — real Payme merchant JSON-RPC API.

Flow:
1. create_payment → CheckPerformTransaction + CreateTransaction (api.payme.uz),
   then redirect the customer to the hosted checkout page.
2. Webhook/notification → authenticate the caller, then RE-QUERY
   GetTransaction on Payme's API and treat Payme's authoritative state as the
   only source of truth (verify-then-confirm; never trust a raw POST body).

Amounts on Payme's API are in TIYIN (1 UZS = 100 tiyin).
Requires PAYME_MERCHANT_ID + PAYME_SECRET.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict

import httpx

from vyron.config import settings
from vyron.errors import PaymentError, ProviderNotConfiguredError, WebhookVerificationError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.payments.base import (
    PaymentProvider,
    PaymentRequest,
    PaymentResult,
    RefundResult,
    WebhookEvent,
    WebhookRequest,
)

log = get_logger("vyron.payments.payme")

API_URL = "https://api.payme.uz"
CHECKOUT_URL = "https://checkout.payme.uz/{transaction_id}"

# Payme transaction states (merchant API)
STATE_CREATED = 1
STATE_PAID = 2
STATE_CANCELLED = 3
STATE_CANCELLED_AFTER_PAYMENT = 4


def _to_tiyin(amount: Decimal) -> int:
    return int((to_money(amount) * 100).quantize(Decimal("1")))


def _from_tiyin(tiyin: Any) -> Decimal:
    return (Decimal(str(tiyin)) / 100).quantize(Decimal("0.01"))


class PaymeProvider(PaymentProvider):
    name = "payme"
    display_name = "Payme"
    currency = "UZS"

    def __init__(self) -> None:
        self.merchant_id = settings.payme_merchant_id
        self.secret = settings.payme_secret

    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.secret)

    def _ensure(self) -> None:
        if not self.is_configured():
            raise ProviderNotConfiguredError(
                "Payme is not configured (PAYME_MERCHANT_ID / PAYME_SECRET missing).",
                code="PAYMENT_PROVIDER_NOT_CONFIGURED",
            )

    def _rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"X-Auth": f"{self.merchant_id}:{self.secret}", "Content-Type": "application/json"}
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        with httpx.Client(timeout=30) as client:
            response = client.post(API_URL, headers=headers, json=body)
        if response.status_code in (401, 403):
            raise ProviderNotConfiguredError("Payme rejected the merchant credentials.", code="PAYMENT_PROVIDER_ERROR")
        if response.status_code >= 400:
            raise PaymentError(f"Payme API error ({response.status_code}).", code="PAYMENT_PROVIDER_ERROR")
        payload = response.json()
        if "error" in payload and payload["error"]:
            err = payload["error"]
            raise PaymentError(
                f"Payme error {err.get('code')}: {err.get('message', err.get('data', ''))}",
                code="PAYMENT_PROVIDER_ERROR",
                details={"payme_code": err.get("code")},
            )
        return payload.get("result", {})

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        self._ensure()
        if request.currency.upper() != "UZS":
            raise PaymentError("Payme only supports UZS payments.", code="PAYMENT_CURRENCY_UNSUPPORTED")
        account = request.metadata.get("order_number") or request.payment_id
        tiyin = _to_tiyin(request.amount)

        # 1) verify Payme accepts this transaction (amount, account)
        self._rpc("CheckPerformTransaction", {"account": account, "amount": tiyin})
        # 2) create it
        result = self._rpc("CreateTransaction", {"account": account, "amount": tiyin})
        transaction = result.get("transaction", "")
        state = result.get("state")
        status = "PAID" if state == STATE_PAID else "PENDING"
        checkout = CHECKOUT_URL.format(transaction_id=transaction) if transaction else None
        return PaymentResult(
            provider=self.name,
            status=status,
            provider_payment_id=transaction or None,
            checkout_url=checkout,
            amount=request.amount,
            currency="UZS",
            raw={"state": state},
        )

    def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self._ensure()
        result = self._rpc("GetTransaction", {"transaction": provider_payment_id})
        state = result.get("state")
        status_map = {
            STATE_CREATED: "PENDING",
            STATE_PAID: "PAID",
            STATE_CANCELLED: "CANCELLED",
            STATE_CANCELLED_AFTER_PAYMENT: "CANCELLED",
        }
        amount = _from_tiyin(result["amount"]) if result.get("amount") is not None else None
        return PaymentResult(
            provider=self.name,
            status=status_map.get(state, "FAILED"),
            provider_payment_id=result.get("transaction") or provider_payment_id,
            amount=amount,
            currency="UZS" if amount is not None else None,
            raw={"state": state, "pay_time": result.get("pay_time")},
        )

    def parse_webhook(self, request: WebhookRequest) -> WebhookEvent:
        """Payme merchant notifications.

        Security: authenticate the caller when Payme sends credentials, then
        RE-QUERY GetTransaction — Payme's API response is the source of truth.
        A notification we cannot re-confirm is rejected.
        """
        self._ensure()
        auth_header = request.headers.get("x-auth", "")
        if auth_header and auth_header != f"{self.merchant_id}:{self.secret}":
            raise WebhookVerificationError("Payme notification auth mismatch.")

        try:
            payload: Dict[str, Any] = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            payload = {}

        # Payme notification shapes: {"type": 0|1, "transaction": "...", "order_id": ...}
        # or JSON-RPC style {"method": "...", "params": {...}}
        params: Dict[str, Any] = payload.get("params") if isinstance(payload.get("params"), dict) else payload
        transaction = str(params.get("transaction") or params.get("id") or "")
        notify_type = params.get("type")
        if not transaction:
            raise WebhookVerificationError("Payme notification has no transaction reference.")

        # verify-then-confirm: authoritative state comes from Payme's API
        confirmed = self.verify_payment(transaction)
        if notify_type == 0 and confirmed.status == "PENDING":
            status = "PENDING"
            event_type = "PAYMENT_PREPARED"
        elif confirmed.status == "PAID":
            status = "PAID"
            event_type = "PAYMENT_PAID"
        elif confirmed.status == "CANCELLED":
            status = "CANCELLED"
            event_type = "PAYMENT_CANCELLED"
        else:
            status = confirmed.status
            event_type = "PAYMENT_STATE_UNKNOWN"

        event_id = f"payme-{transaction}-{notify_type if notify_type is not None else confirmed.raw.get('state')}"
        return WebhookEvent(
            provider=self.name,
            event_id=event_id,
            event_type=event_type,
            status=status,
            merchant_reference=None,
            provider_payment_id=transaction,
            amount=confirmed.amount,
            currency=confirmed.currency,
            raw={"notify_type": notify_type, "confirmed_status": confirmed.status},
        )

    def refund_payment(
        self, provider_payment_id: str, amount: Decimal, reason: str, idempotency_key: str | None = None
    ) -> RefundResult:
        self._ensure()
        # Payme merchant API: CancelTransaction after payment performs a refund.
        result = self._rpc("CancelTransaction", {"transaction": provider_payment_id, "reason": reason[:200]})
        state = result.get("state")
        return RefundResult(
            provider=self.name,
            status="COMPLETED" if state in (STATE_CANCELLED, STATE_CANCELLED_AFTER_PAYMENT) else "PROCESSING",
            provider_refund_id=provider_payment_id,
            amount=amount,
            raw={"state": state},
        )
