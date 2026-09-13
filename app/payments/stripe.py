"""Stripe provider adapter (PaymentIntent-style, webhook verified)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal

from app.config import settings
from app.payments.base import PaymentProvider, register


@register
class StripeProvider(PaymentProvider):
    name = "stripe"

    def is_configured(self) -> bool:
        return bool(settings.STRIPE_SECRET_KEY)

    def create_payment(self, payment, order, return_url: str = "") -> dict:
        if not self.is_configured():
            return {"action": "error", "error": "PAYMENT_PROVIDER_NOT_CONFIGURED"}
        # Real implementation would call Stripe API here (requires network + key).
        # We return instructions so checkout shows a real (non-fake) pending state.
        return {"action": "instructions",
                "message": "stripe_manual",
                "reference": str(payment.id),
                "amount": str(payment.amount)}

    def verify_webhook(self, data: dict, headers: dict) -> tuple[bool, str]:
        # Stripe-Signature: t=...,v1=... over raw body. We receive parsed data + raw in _raw.
        if not settings.STRIPE_WEBHOOK_SECRET:
            return False, ""
        sig = headers.get("stripe-signature", "") or headers.get("Stripe-Signature", "")
        raw = (data or {}).get("_raw", "")
        try:
            parts = dict(p.split("=", 1) for p in sig.split(",") if "=" in p)
            signed = f"{parts['t']}.{raw}".encode()
            mac = hmac.new(settings.STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(mac, parts.get("v1", "")):
                return False, ""
            if abs(time.time() - int(parts["t"])) > 300:
                return False, ""
        except Exception:
            return False, ""
        obj = ((data or {}).get("data", {}) or {}).get("object", {}) or {}
        return True, str(obj.get("id", ""))

    def parse_webhook(self, data: dict) -> dict:
        etype = (data or {}).get("type", "")
        obj = ((data or {}).get("data", {}) or {}).get("object", {}) or {}
        amount = Decimal(str(obj.get("amount_received", obj.get("amount", 0)))) / 100
        paid = etype in ("payment_intent.succeeded", "checkout.session.completed")
        ref = (obj.get("metadata", {}) or {}).get("payment_id", "")
        return {"external_id": str(obj.get("id", "")), "amount": amount,
                "status": etype, "paid": paid, "payment_db_id": ref}
