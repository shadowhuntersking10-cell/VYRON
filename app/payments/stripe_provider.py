"""Stripe provider (PaymentIntent-based, webhook verified via HMAC)."""
from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal

import httpx

from app.config import settings
from app.payments.base import PaymentProvider, PaymentResult, ProviderError

STRIPE_API = "https://api.stripe.com/v1"


class StripeProvider(PaymentProvider):
    name = "stripe"

    def __init__(self) -> None:
        self.secret_key = settings.STRIPE_SECRET_KEY
        self.publishable_key = settings.STRIPE_PUBLISHABLE_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.test_mode = settings.STRIPE_TEST_MODE

    @property
    def configured(self) -> bool:
        return bool(self.secret_key)

    async def create_payment(self, *, amount, currency, order_public_id, return_url=None, meta=None) -> PaymentResult:
        self.require_configured()
        minor = int(Decimal(str(amount)) * 100)
        try:
            async with httpx.AsyncClient(timeout=20, auth=(self.secret_key, "")) as client:
                resp = await client.post(
                    f"{STRIPE_API}/payment_intents",
                    data={
                        "amount": minor,
                        "currency": currency.lower(),
                        "metadata[order]": order_public_id,
                        "automatic_payment_methods[enabled]": "true",
                    },
                )
        except Exception as exc:
            raise ProviderError(f"stripe network error: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise ProviderError(f"stripe http {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return PaymentResult(
            ok=True, provider=self.name, provider_payment_id=data.get("id"),
            checkout_url=None, status="PENDING", raw=data,
        )

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=20, auth=(self.secret_key, "")) as client:
                resp = await client.get(f"{STRIPE_API}/payment_intents/{provider_payment_id}")
        except Exception as exc:
            raise ProviderError(f"stripe network error: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"stripe http {resp.status_code}")
        data = resp.json()
        status = "PAID" if data.get("status") == "succeeded" else "PENDING"
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=provider_payment_id, status=status, raw=data)

    def verify_signature(self, raw_body: bytes, sig_header: str) -> bool:
        if not self.webhook_secret:
            return False
        try:
            parts = dict(p.split("=", 1) for p in sig_header.split(","))
            timestamp, signature = parts["t"], parts["v1"]
            if abs(time.time() - int(timestamp)) > 300:
                return False
            expected = hmac.new(
                self.webhook_secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    async def handle_webhook(self, payload: dict, headers: dict) -> PaymentResult:
        self.require_configured()
        # NOTE: signature must be checked by the route using raw body + verify_signature.
        obj = (payload.get("data", {}) or {}).get("object", {}) or {}
        status = "PAID" if payload.get("type") == "payment_intent.succeeded" else "PENDING"
        return PaymentResult(
            ok=True, provider=self.name,
            provider_payment_id=obj.get("id"), status=status, raw=payload,
        )

    async def refund_payment(self, provider_payment_id: str, amount=None) -> PaymentResult:
        self.require_configured()
        data = {"payment_intent": provider_payment_id}
        if amount is not None:
            data["amount"] = int(Decimal(str(amount)) * 100)
        try:
            async with httpx.AsyncClient(timeout=20, auth=(self.secret_key, "")) as client:
                resp = await client.post(f"{STRIPE_API}/refunds", data=data)
        except Exception as exc:
            raise ProviderError(f"stripe network error: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise ProviderError(f"stripe http {resp.status_code}: {resp.text[:300]}")
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=provider_payment_id, status="REFUNDED", raw=resp.json())
