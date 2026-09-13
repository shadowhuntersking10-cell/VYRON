"""Payment provider abstraction. Every provider implements this interface.

CRITICAL: no provider may fake success. If credentials are missing the
provider reports `configured=False` and the API surfaces
"Payment provider not configured".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class ProviderNotConfigured(RuntimeError):
    pass


class ProviderError(RuntimeError):
    pass


@dataclass
class PaymentResult:
    ok: bool
    provider: str
    provider_payment_id: str | None = None
    checkout_url: str | None = None
    status: str = "PENDING"
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class PaymentProvider:
    name: str = "base"

    @property
    def configured(self) -> bool:
        return False

    def require_configured(self) -> None:
        if not self.configured:
            raise ProviderNotConfigured(f"Payment provider not configured: {self.name}")

    async def create_payment(
        self, *, amount: Decimal, currency: str, order_public_id: str,
        return_url: str | None = None, meta: dict | None = None,
    ) -> PaymentResult:
        raise NotImplementedError

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        raise NotImplementedError

    async def handle_webhook(self, payload: dict, headers: dict) -> PaymentResult:
        raise NotImplementedError

    async def refund_payment(self, provider_payment_id: str, amount: Decimal | None = None) -> PaymentResult:
        raise NotImplementedError
