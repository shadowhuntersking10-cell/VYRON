"""Click adapter (Uzbekistan) — real Click merchant integration.

Implements the documented merchant prepare/complete callback scheme with MD5
signatures plus invoice creation via the Click merchant API:

- prepare callback:  sign == md5(transaction_id + secret_key)
- complete callback: sign == md5(transaction_id + secret_key + merchant_trans_id
                                + amount + action + sign_time)

Amount is validated against the stored Payment — a mismatched amount never
marks anything as paid. Requires CLICK_MERCHANT_ID + CLICK_SERVICE_ID + CLICK_SECRET.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Dict, Optional

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

log = get_logger("vyron.payments.click")

API_BASE = "https://api.click.uz/v2/merchant"
PAY_PAGE = "https://my.click.uz/services/{invoice_id}"


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


class ClickProvider(PaymentProvider):
    name = "click"
    display_name = "Click"
    currency = "UZS"

    def __init__(self) -> None:
        self.merchant_id = settings.click_merchant_id
        self.service_id = settings.click_service_id
        self.secret = settings.click_secret

    def is_configured(self) -> bool:
        return bool(self.merchant_id and self.secret)

    def _ensure(self) -> None:
        if not self.is_configured():
            raise ProviderNotConfiguredError(
                "Click is not configured (CLICK_MERCHANT_ID / CLICK_SECRET missing).",
                code="PAYMENT_PROVIDER_NOT_CONFIGURED",
            )

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        self._ensure()
        if request.currency.upper() != "UZS":
            raise PaymentError("Click only supports UZS payments.", code="PAYMENT_CURRENCY_UNSUPPORTED")
        external_id = request.metadata.get("order_number") or request.payment_id
        data = {
            "merchant_id": int(self.merchant_id),
            "merchant_user_id": int(self.service_id or 1),
            "external_id": str(external_id),
            "amount": str(to_money(request.amount)),
            "description": request.description[:200],
        }
        url = f"{API_BASE}/invoice/create"
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=data, headers=self._auth_headers())
        if response.status_code in (401, 403):
            raise ProviderNotConfiguredError("Click rejected the merchant credentials.", code="PAYMENT_PROVIDER_ERROR")
        if response.status_code >= 400:
            raise PaymentError(f"Click API error ({response.status_code}).", code="PAYMENT_PROVIDER_ERROR")
        payload = response.json()
        if payload.get("error"):
            raise PaymentError(f"Click error: {payload.get('error_note') or payload.get('error')}", code="PAYMENT_PROVIDER_ERROR")
        invoice_id = str(payload.get("id") or payload.get("invoice_id") or "")
        return PaymentResult(
            provider=self.name,
            status="PENDING",
            provider_payment_id=invoice_id or None,
            checkout_url=PAY_PAGE.format(invoice_id=invoice_id) if invoice_id else None,
            amount=request.amount,
            currency="UZS",
            raw={"invoice": payload},
        )

    def _auth_headers(self) -> Dict[str, str]:
        import base64

        token = base64.b64encode(f"{self.merchant_id}:{self.secret}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self._ensure()
        url = f"{API_BASE}/invoice/{provider_payment_id}"
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=self._auth_headers())
        if response.status_code >= 400:
            raise PaymentError(f"Click API error ({response.status_code}).", code="PAYMENT_PROVIDER_ERROR")
        payload = response.json()
        status_value = str(payload.get("status", "")).lower()
        if status_value in {"paid", "completed", "2"}:
            status = "PAID"
        elif status_value in {"cancelled", "canceled", "rejected", "-1"}:
            status = "CANCELLED"
        else:
            status = "PENDING"
        amount = Decimal(str(payload["amount"])) if payload.get("amount") is not None else None
        return PaymentResult(
            provider=self.name,
            status=status,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency="UZS" if amount is not None else None,
            raw={"invoice_status": status_value},
        )

    def parse_webhook(self, request: WebhookRequest) -> WebhookEvent:
        """Click prepare/complete callbacks (form-encoded or JSON)."""
        self._ensure()
        params = self._extract_params(request)
        action = str(params.get("action", ""))
        transaction_id = str(params.get("transaction_id", ""))
        merchant_trans_id = str(params.get("merchant_trans_id", ""))
        amount_raw = params.get("amount", "")
        sign_time = str(params.get("sign_time", ""))
        signature = str(params.get("signature", ""))

        if not transaction_id or not signature:
            raise WebhookVerificationError("Click callback missing required fields.")

        if action == "0":  # prepare
            expected = _md5(transaction_id + self.secret)
            if not _eq(expected, signature):
                raise WebhookVerificationError("Click prepare signature mismatch.")
            event_type = "PAYMENT_PREPARED"
            status = "PENDING"
        elif action == "1":  # complete
            expected = _md5(transaction_id + self.secret + merchant_trans_id + str(amount_raw) + action + sign_time)
            if not _eq(expected, signature):
                raise WebhookVerificationError("Click complete signature mismatch.")
            error_code = params.get("error")
            if error_code in (None, "", "0", 0):
                event_type, status = "PAYMENT_PAID", "PAID"
            else:
                error_note = params.get("error_note", "")
                if str(error_code) == "-5017":
                    event_type, status = "PAYMENT_CANCELLED", "CANCELLED"
                else:
                    event_type, status = "PAYMENT_FAILED", "FAILED"
                log.warning(f"click callback error {error_code}: {error_note}")
        else:
            raise WebhookVerificationError(f"Unknown Click action '{action}'.")

        amount: Optional[Decimal] = None
        try:
            amount = to_money(amount_raw) if str(amount_raw) != "" else None
        except Exception:
            amount = None

        return WebhookEvent(
            provider=self.name,
            event_id=f"click-{transaction_id}-{action}-{sign_time or '0'}",
            event_type=event_type,
            status=status,
            merchant_reference=merchant_trans_id or None,
            provider_payment_id=transaction_id,
            amount=amount,
            currency="UZS" if amount is not None else None,
            raw={"action": action, "error": params.get("error")},
        )

    @staticmethod
    def _extract_params(request: WebhookRequest) -> Dict[str, Any]:
        from urllib.parse import parse_qs

        body_text = request.body.decode("utf-8", errors="replace")
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                parsed = json.loads(body_text or "{}")
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass
        parsed_qs = parse_qs(body_text, keep_blank_values=True)
        if parsed_qs:
            return {k: v[0] for k, v in parsed_qs.items()}
        # fallback: query string
        return dict(request.query)

    def refund_payment(
        self, provider_payment_id: str, amount: Decimal, reason: str, idempotency_key: str | None = None
    ) -> RefundResult:
        self._ensure()
        url = f"{API_BASE}/invoice/{provider_payment_id}/reject"
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json={"reason": reason[:200]}, headers=self._auth_headers())
        if response.status_code >= 400:
            raise PaymentError(f"Click refund error ({response.status_code}).", code="PAYMENT_PROVIDER_ERROR")
        payload = response.json()
        return RefundResult(
            provider=self.name,
            status="COMPLETED" if not payload.get("error") else "FAILED",
            provider_refund_id=str(payload.get("id") or provider_payment_id),
            amount=amount,
            raw=payload,
        )


def _eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.lower(), b.lower())
