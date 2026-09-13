"""Telegram Stars adapter (for digital goods inside Telegram Mini Apps).

Real charging happens through Bot API createInvoiceLink/sendInvoice; this
adapter exposes configuration status and invoice metadata. Webhook
confirmation arrives via Telegram successful_payment updates.
"""
from __future__ import annotations

from decimal import Decimal

from app.config import settings
from app.payments.base import PaymentProvider, register


@register
class StarsProvider(PaymentProvider):
    name = "stars"

    def is_configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN)

    def create_payment(self, payment, order, return_url: str = "") -> dict:
        if not self.is_configured():
            return {"action": "error", "error": "PAYMENT_PROVIDER_NOT_CONFIGURED"}
        return {"action": "stars_invoice", "reference": str(payment.id),
                "amount": str(payment.amount), "currency": "XTR"}

    def verify_webhook(self, data: dict, headers: dict) -> tuple[bool, str]:
        # Telegram updates are verified by secret token header when webhook is set.
        # Real verification happens in the bot update handler.
        return True, str((data or {}).get("telegram_payment_charge_id", ""))

    def parse_webhook(self, data: dict) -> dict:
        d = data or {}
        return {"external_id": str(d.get("telegram_payment_charge_id", "")),
                "amount": Decimal(str(d.get("total_amount", 0))),
                "status": "successful_payment", "paid": True,
                "payment_db_id": (d.get("invoice_payload", "") or "").replace("VYRON:", "")}
