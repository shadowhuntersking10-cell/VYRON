"""Payme provider adapter (JSON-RPC protocol subset)."""
from __future__ import annotations

import base64
from decimal import Decimal

from app.config import settings
from app.payments.base import PaymentProvider, register


@register
class PaymeProvider(PaymentProvider):
    name = "payme"

    def is_configured(self) -> bool:
        return bool(settings.PAYME_MERCHANT_ID and settings.PAYME_SECRET)

    def create_payment(self, payment, order, return_url: str = "") -> dict:
        if not self.is_configured():
            return {"action": "error", "error": "PAYMENT_PROVIDER_NOT_CONFIGURED"}
        amount_tiyin = int(Decimal(str(payment.amount)) * 100)
        params = f"m={settings.PAYME_MERCHANT_ID};ac.order_id={payment.id};a={amount_tiyin}"
        encoded = base64.b64encode(params.encode()).decode()
        url = f"https://checkout.paycom.uz/{encoded}"
        return {"action": "redirect", "url": url}

    def verify_webhook(self, data: dict, headers: dict) -> tuple[bool, str]:
        auth = headers.get("authorization", "") or headers.get("Authorization", "")
        # Payme sends Basic base64(login:key); we check the key part against secret.
        try:
            scheme, _, encoded = auth.partition(" ")
            decoded = base64.b64decode(encoded).decode() if scheme.lower() == "basic" else ""
            _, _, key = decoded.partition(":")
            import hmac as _hmac
            if not _hmac.compare_digest(key, settings.PAYME_SECRET):
                return False, ""
        except Exception:
            return False, ""
        params = (data or {}).get("params", {})
        account = params.get("account", {})
        return True, str(account.get("order_id", "") or params.get("id", ""))

    def parse_webhook(self, data: dict) -> dict:
        method = (data or {}).get("method", "")
        params = (data or {}).get("params", {})
        account = params.get("account", {})
        amount = Decimal(str(params.get("amount", 0))) / 100
        paid = method in ("PerformTransaction",)
        return {"external_id": str(params.get("id", "")), "amount": amount,
                "status": method, "paid": paid, "payment_db_id": account.get("order_id")}
