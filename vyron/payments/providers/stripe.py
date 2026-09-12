"""Stripe adapter — real Stripe REST API via httpx.

Implements Checkout Sessions (hosted payment page) + webhook signature
verification (Stripe-Signature: t=...,v1=...) exactly per Stripe's spec.
Requires STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET for webhooks).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx

from vyron.config import settings
from vyron.errors import ProviderNotConfiguredError, WebhookVerificationError
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

log = get_logger("vyron.payments.stripe")

API_BASE = "https://api.stripe.com/v1"
WEBHOOK_TOLERANCE_SECONDS = 300

STATUS_MAP = {
    "complete": "PAID",
    "paid": "PAID",
    "succeeded": "PAID",
    "open": "PENDING",
    "processing": "PENDING",
    "requires_payment_method": "FAILED",
    "requires_confirmation": "PENDING",
    "requires_action": "PENDING",
    "expired": "EXPIRED",
    "canceled": "CANCELLED",
}


class StripeProvider(PaymentProvider):
    name = "stripe"
    display_name = "Stripe"

    def __init__(self) -> None:
        self.secret_key = settings.stripe_secret_key
        self.webhook_secret = settings.stripe_webhook_secret

    def is_configured(self) -> bool:
        return bool(self.secret_key)

    def _ensure(self) -> None:
        if not self.is_configured():
            raise ProviderNotConfiguredError(
                "Stripe is not configured (STRIPE_SECRET_KEY missing).", code="PAYMENT_PROVIDER_NOT_CONFIGURED"
            )

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.secret_key}"}

    def _zero_decimal(self, currency: str) -> bool:
        return currency.upper() in {"UZS", "JPY", "KRW", "CLP", "HUF", "VND", "RUB"}

    def _minor_units(self, amount: Decimal, currency: str) -> int:
        if self._zero_decimal(currency):
            return int(to_money(amount).quantize(Decimal("1")))
        return int((to_money(amount) * 100).quantize(Decimal("1")))

    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        self._ensure()
        currency = request.currency.upper()
        data = {
            "mode": "payment",
            "client_reference_id": request.payment_id,
            "success_url": request.return_url,
            "cancel_url": request.cancel_url,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(self._minor_units(request.amount, currency)),
            "line_items[0][price_data][product_data][name]": request.description[:250],
            "metadata[payment_id]": request.payment_id,
        }
        if request.idempotency_key:
            headers = {**self._headers(), "Idempotency-Key": request.idempotency_key}
        else:
            headers = self._headers()
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{API_BASE}/checkout/sessions", headers=headers, data=data)
        if response.status_code >= 400:
            log.error(f"stripe create failed: {response.status_code} {response.text[:300]}")
            raise ProviderNotConfiguredError(
                "Stripe rejected the payment creation request.", code="PAYMENT_CREATE_FAILED"
            ) if response.status_code in (401, 403) else _stripe_error(response)
        payload = response.json()
        status = STATUS_MAP.get(payload.get("status", ""), "PENDING")
        if payload.get("payment_status") == "paid":
            status = "PAID"
        return PaymentResult(
            provider=self.name,
            status=status,
            provider_payment_id=payload.get("id"),
            checkout_url=payload.get("url"),
            amount=request.amount,
            currency=currency,
            raw={"id": payload.get("id"), "status": payload.get("status"), "payment_status": payload.get("payment_status")},
        )

    def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self._ensure()
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{API_BASE}/checkout/sessions/{provider_payment_id}", headers=self._headers()
            )
        if response.status_code == 404:
            return PaymentResult(provider=self.name, status="FAILED", provider_payment_id=provider_payment_id, raw={})
        if response.status_code >= 400:
            _stripe_error(response)
        payload = response.json()
        status = STATUS_MAP.get(payload.get("status", ""), "PENDING")
        if payload.get("payment_status") == "paid":
            status = "PAID"
        amount = None
        if payload.get("amount_total") is not None:
            amount = Decimal(payload["amount_total"]) / (Decimal(1) if self._zero_decimal(payload.get("currency") or "usd") else Decimal(100))
        return PaymentResult(
            provider=self.name,
            status=status,
            provider_payment_id=payload.get("id"),
            amount=amount,
            currency=(payload.get("currency") or "").upper() or None,
            raw={"status": payload.get("status"), "payment_status": payload.get("payment_status")},
        )

    def parse_webhook(self, request: WebhookRequest) -> WebhookEvent:
        signature_header = request.headers.get("stripe-signature", "")
        if not signature_header or not self.webhook_secret:
            raise WebhookVerificationError("Missing Stripe signature or webhook secret.")
        self._verify_signature(signature_header, request.body)
        import json

        try:
            event = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise WebhookVerificationError("Webhook body is not valid JSON.") from exc

        event_type = str(event.get("type", ""))
        data_obj: Dict[str, Any] = (event.get("data") or {}).get("object") or {}
        event_id = str(event.get("id", ""))
        if not event_id:
            raise WebhookVerificationError("Webhook event has no id.")

        status = "FAILED"
        if event_type in {"checkout.session.completed", "payment_intent.succeeded", "charge.succeeded", "invoice.paid"}:
            status = "PAID"
        elif event_type in {"checkout.session.async_payment_succeeded",}:
            status = "PAID"
        elif event_type in {"charge.refunded", "charge.refund.updated"}:
            status = "REFUNDED"
        elif event_type in {"payment_intent.payment_failed", "charge.failed", "checkout.session.expired"}:
            status = "FAILED"
        elif event_type in {"checkout.session.async_payment_failed"}:
            status = "FAILED"
        else:
            status = "INFO"

        amount = None
        for key in ("amount_total", "amount_received", "amount"):
            if data_obj.get(key) is not None:
                raw_amount = Decimal(str(data_obj[key]))
                currency = (data_obj.get("currency") or "usd").upper()
                amount = raw_amount if self._zero_decimal(currency) else raw_amount / Decimal(100)
                break

        merchant_reference = (
            data_obj.get("client_reference_id")
            or (data_obj.get("metadata") or {}).get("payment_id")
            or None
        )
        provider_payment_id = data_obj.get("id") or data_obj.get("payment_intent")

        return WebhookEvent(
            provider=self.name,
            event_id=event_id,
            event_type=event_type,
            status=status,
            merchant_reference=str(merchant_reference) if merchant_reference else None,
            provider_payment_id=str(provider_payment_id) if provider_payment_id else None,
            amount=amount,
            currency=(data_obj.get("currency") or "").upper() or None,
            raw={"type": event_type},
        )

    def _verify_signature(self, header: str, body: bytes) -> None:
        timestamp: Optional[str] = None
        signatures = []
        for part in header.split(","):
            key, _, value = part.partition("=")
            if key.strip() == "t":
                timestamp = value.strip()
            elif key.strip() == "v1":
                signatures.append(value.strip())
        if not timestamp or not signatures:
            raise WebhookVerificationError("Malformed Stripe-Signature header.")
        try:
            ts = int(timestamp)
        except ValueError as exc:
            raise WebhookVerificationError("Invalid Stripe signature timestamp.") from exc
        if abs(time.time() - ts) > WEBHOOK_TOLERANCE_SECONDS:
            raise WebhookVerificationError("Stripe webhook timestamp outside tolerance (replay?).")
        signed_payload = f"{timestamp}.".encode() + body
        expected = hmac.new(self.webhook_secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise WebhookVerificationError("Stripe webhook signature mismatch.")

    def refund_payment(
        self, provider_payment_id: str, amount: Decimal, reason: str, idempotency_key: Optional[str] = None
    ) -> RefundResult:
        self._ensure()
        session = self.verify_payment(provider_payment_id)
        currency = session.currency or "USD"
        data: Dict[str, Any] = {"amount": str(self._minor_units(amount, currency)), "reason": "requested_by_customer"}
        # Refund against the underlying payment_intent when available.
        payment_intent = session.raw.get("payment_intent") or provider_payment_id
        data["payment_intent"] = payment_intent
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{API_BASE}/refunds", headers=headers, data=data)
        if response.status_code >= 400:
            _stripe_error(response)
        payload = response.json()
        return RefundResult(
            provider=self.name,
            status="COMPLETED" if payload.get("status") == "succeeded" else "PROCESSING",
            provider_refund_id=payload.get("id"),
            amount=amount,
            raw={"status": payload.get("status")},
        )


def _stripe_error(response: httpx.Response):
    from vyron.errors import PaymentError

    try:
        message = response.json().get("error", {}).get("message", response.text[:200])
    except ValueError:
        message = response.text[:200]
    raise PaymentError(f"Stripe API error: {message}", code="PAYMENT_PROVIDER_ERROR")
