"""Click provider architecture (Uzbekistan)."""
from __future__ import annotations

import hashlib
from decimal import Decimal

import httpx

from app.config import settings
from app.payments.base import PaymentProvider, PaymentResult, ProviderError


class ClickProvider(PaymentProvider):
    name = "click"

    def __init__(self) -> None:
        self.merchant_id = settings.CLICK_MERCHANT_ID
        self.service_id = settings.CLICK_SERVICE_ID
        self.secret_key = settings.CLICK_SECRET_KEY
        self.test_mode = settings.CLICK_TEST_MODE

    @property
    def configured(self) -> bool:
        return bool(self.merchant_id and self.secret_key)

    async def create_payment(self, *, amount, currency, order_public_id, return_url=None, meta=None) -> PaymentResult:
        self.require_configured()
        url = (
            "https://my.click.uz/services/pay"
            f"?service_id={self.service_id}&merchant_id={self.merchant_id}"
            f"&amount={amount}&transaction_param={order_public_id}"
        )
        if return_url:
            url += f"&return_url={return_url}"
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=order_public_id, checkout_url=url, status="PENDING")

    def _sign(self, *parts: str) -> str:
        raw = "".join(parts) + self.secret_key
        return hashlib.md5(raw.encode()).hexdigest()

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self.require_configured()
        # Click verifies via webhook callbacks; direct verify endpoint per docs.
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=provider_payment_id, status="PENDING", raw={})

    async def handle_webhook(self, payload: dict, headers: dict) -> PaymentResult:
        self.require_configured()
        sign = payload.get("sign_string") or payload.get("sign") or ""
        expected = self._sign(
            str(payload.get("click_trans_id", "")),
            str(payload.get("service_id", "")),
            str(payload.get("merchant_trans_id", "")),
            str(payload.get("amount", "")),
            str(payload.get("action", "")),
        )
        order_id = str(payload.get("merchant_trans_id", ""))
        if sign and sign != expected:
            return PaymentResult(ok=False, provider=self.name, status="FAILED", error="bad_signature", raw=payload)
        action = str(payload.get("action", ""))
        status = "PAID" if action == "1" else "PENDING"
        return PaymentResult(ok=True, provider=self.name, provider_payment_id=order_id, status=status, raw=payload)

    async def refund_payment(self, provider_payment_id: str, amount=None) -> PaymentResult:
        self.require_configured()
        raise ProviderError("Click refunds are processed via merchant cabinet / support flow")
