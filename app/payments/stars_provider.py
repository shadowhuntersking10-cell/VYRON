"""Telegram Stars provider (XTR invoices sent by the VYRON bot).

Flow: `create_payment` does NOT charge anything - it prices the order in
Stars and returns a deep link to the bot (`?start=pay_<public_id>`). The bot
sends a real Telegram invoice (currency XTR); settlement happens in the
`successful_payment` handler, which reuses the same `_settle_paid` pipeline
as every other provider. Nothing is ever faked.
"""
from __future__ import annotations

from decimal import Decimal

from app.config import settings
from app.payments.base import PaymentProvider, PaymentResult
from app.utils.money import D

STARS_PER_USD_DEFAULT = 50  # ~$0.02 per Star
UZS_PER_USD_FALLBACK = D(12900)


def stars_for_amount(amount: Decimal, currency: str, uzs_per_usd: Decimal | None = None) -> int:
    """Server-side conversion of an order total into whole Stars (min 1)."""
    amount = D(amount)
    currency = (currency or "UZS").upper()
    if currency == "USD":
        usd = amount
    else:
        usd = amount / (uzs_per_usd or UZS_PER_USD_FALLBACK)
    return max(1, int(usd * STARS_PER_USD_DEFAULT))


class StarsProvider(PaymentProvider):
    name = "stars"

    @property
    def configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN)

    @property
    def bot_username(self) -> str:
        return (settings.TELEGRAM_BOT_USERNAME or "").lstrip("@")

    def pay_link(self, order_public_id: str) -> str | None:
        if not self.bot_username:
            return None
        return f"https://t.me/{self.bot_username}?start=pay_{order_public_id}"

    async def create_payment(
        self, *, amount: Decimal, currency: str, order_public_id: str,
        return_url: str | None = None, meta: dict | None = None,
    ) -> PaymentResult:
        self.require_configured()
        stars = stars_for_amount(D(amount), currency)
        link = self.pay_link(order_public_id)
        if not link:
            return PaymentResult(ok=False, provider=self.name, status="ERROR",
                                 error="stars_bot_username_missing")
        return PaymentResult(
            ok=True, provider=self.name,
            provider_payment_id=f"stars:{order_public_id}",
            checkout_url=link, status="PENDING",
            raw={"stars": stars, "currency": currency, "amount": str(amount),
                 "bot": self.bot_username, "invoice_payload": order_public_id},
        )

    async def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        self.require_configured()
        # Stars payments are verified by Telegram itself via pre_checkout /
        # successful_payment updates - there is nothing to poll.
        return PaymentResult(ok=False, provider=self.name, status="UNKNOWN",
                             error="stars_verified_via_bot_only")

    async def handle_webhook(self, payload: dict, headers: dict) -> PaymentResult:
        raise NotImplementedError("stars_settled_via_bot_handlers")

    async def refund_payment(self, provider_payment_id: str, amount: Decimal | None = None) -> PaymentResult:
        self.require_configured()
        # Telegram Stars support refunds via refundStarPayment; requires the
        # telegram payment charge id captured at settlement time. Surface an
        # explicit state when it is unavailable instead of faking a refund.
        return PaymentResult(ok=False, provider=self.name, status="ERROR",
                             error="stars_refund_requires_charge_id")
