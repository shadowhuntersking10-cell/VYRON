"""Click provider adapter."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from app.config import settings
from app.payments.base import PaymentProvider, register


@register
class ClickProvider(PaymentProvider):
    name = "click"

    def is_configured(self) -> bool:
        return bool(settings.CLICK_MERCHANT_ID and settings.CLICK_SECRET and settings.CLICK_SERVICE_ID)

    def create_payment(self, payment, order, return_url: str = "") -> dict:
        if not self.is_configured():
            return {"action": "error", "error": "PAYMENT_PROVIDER_NOT_CONFIGURED"}
        url = (
            "https://my.click.uz/services/pay"
            f"?service_id={settings.CLICK_SERVICE_ID}"
            f"&merchant_id={settings.CLICK_MERCHANT_ID}"
            f"&amount={payment.amount}&transaction_param={payment.id}"
        )
        if return_url:
            url += f"&return_url={return_url}"
        return {"action": "redirect", "url": url}

    def verify_webhook(self, data: dict, headers: dict) -> tuple[bool, str]:
        d = data or {}
        sign = str(d.get("sign_string", ""))
        # Click sign: md5(click_trans_id+service_id+secret+merchant_trans_id+amount+action+sign_time)
        raw = (f"{d.get('click_trans_id','')}{d.get('service_id','')}{settings.CLICK_SECRET}"
               f"{d.get('merchant_trans_id','')}{d.get('amount','')}{d.get('action','')}{d.get('sign_time','')}")
        calc = hashlib.md5(raw.encode()).hexdigest()
        import hmac as _hmac
        ok = _hmac.compare_digest(calc, sign)
        return ok, str(d.get("merchant_trans_id", ""))

    def parse_webhook(self, data: dict) -> dict:
        d = data or {}
        paid = str(d.get("action", "")) == "1" and str(d.get("error", "0")) == "0"
        return {"external_id": str(d.get("click_trans_id", "")), "amount": Decimal(str(d.get("amount", 0))),
                "status": str(d.get("action", "")), "paid": paid, "payment_db_id": d.get("merchant_trans_id")}
