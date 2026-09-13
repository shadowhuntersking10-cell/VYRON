"""Payme provider (JSON-RPC API architecture).

Implements request building + signature verification. Real network calls are
made only when credentials are configured; otherwise raises
ProviderNotConfigured and the platform shows "not configured".
"""
from __future__ import annotations

import base64
from decimal import Decimal

import httpx

from app.config import settings
from app.payments.base import PaymentProvider, PaymentResult, ProviderError

PAYME_API_URL = "https://checkout.paycom.uz/api"


class PaymeProvider(PaymentProvider):
    name = "payme"

    def __init__(self) -> None:
        self.merchant_id = settings.PAYME_MERCHANT_ID
        self.secret_key = settings.PAYME_SECRET_KEY
        self.test_mode = settings.PAYME_TEST_MODE

    @property
    def configured(self) -> bool:
        return bool(self.merchant_id and self.secret_key)

    def _auth_header(self) -> str:
        raw = f"{self.merchant_id}:{self.secret_key}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    async def create_payment(self, *, amount, currency, order_public_id, return_url=None, meta=None) -> PaymentResult:
        self.require_configured()
        # Payme checkout link format (amount in tiyin for UZS)
        tiyin = int(Decimal(str(amount)) * 100)
        url = f"https://checkout.paycom.uz/{self.merchant_id}?a={tiyin}&o={order_public_id}"
        if return_url:
            url += f"&c={return_url}"
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=order_public_id, checkout_url=url, status="PENDING")

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    PAYME_API_URL,
                    headers={"X-Auth": self._auth_header(), "Content-Type": "application/json"},
                    json={
                        "method": "receipts.get",
                        "params": {"id": provider_payment_id},
                    },
                )
        except Exception as exc:
            raise ProviderError(f"payme network error: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"payme http {resp.status_code}")
        data = resp.json()
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=provider_payment_id, status="PENDING", raw=data)

    async def handle_webhook(self, payload: dict, headers: dict) -> PaymentResult:
        """Verify Payme JSON-RPC webhook auth (X-Auth must match merchant key)."""
        self.require_configured()
        x_auth = headers.get("x-auth") or headers.get("X-Auth") or ""
        if x_auth != self._auth_header():
            return PaymentResult(ok=False, provider=self.name, status="FAILED", error="bad_signature", raw=payload)
        method = payload.get("method", "")
        params = payload.get("params", {})
        order_id = str(params.get("account", {}).get("order_id") or params.get("id") or "")
        status = "PAID" if method in ("CheckPerformTransaction", "PerformTransaction", "receipts.pay") else "PENDING"
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=order_id, status=status, raw=payload)

    async def refund_payment(self, provider_payment_id: str, amount=None) -> PaymentResult:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    PAYME_API_URL,
                    headers={"X-Auth": self._auth_header(), "Content-Type": "application/json"},
                    json={"method": "receipts.cancel", "params": {"id": provider_payment_id}},
                )
        except Exception as exc:
            raise ProviderError(f"payme network error: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"payme http {resp.status_code}")
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=provider_payment_id, status="REFUNDED", raw=resp.json())
