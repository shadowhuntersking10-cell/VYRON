"""Payment orchestration: create + verified webhooks -> mark PAID (idempotent)."""
from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.payments.base import PROVIDERS
from app.services import orders as order_svc
from app.services.pricing import q
from app.utils.logging import get_logger
from app.utils.security import new_token

log = get_logger("vyron.payments")


class PaymentError(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


def get_provider(name: str):
    p = PROVIDERS.get((name or "").lower())
    if not p:
        raise PaymentError("provider_unknown")
    return p


class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    def statuses(self) -> dict:
        return {name: p.status() for name, p in PROVIDERS.items()}

    def create_for_order(self, order: models.Order, provider_name: str, return_url: str = "") -> tuple[models.Payment, dict]:
        if not settings.PAYMENTS_ENABLED:
            raise PaymentError("payments_disabled")
        if provider_name == "wallet":
            return self._pay_with_wallet(order)
        provider = get_provider(provider_name)
        if not provider.is_configured():
            raise PaymentError("PAYMENT_PROVIDER_NOT_CONFIGURED")
        existing = self.db.query(models.Payment).filter_by(order_id=order.id, provider=provider_name).first()
        if existing and existing.status in ("CREATED", "PENDING"):
            payment = existing
        else:
            payment = models.Payment(
                order_id=order.id, provider=provider_name, status="PENDING",
                amount=q(order.total), currency=order.currency,
                idempotency_key=new_token(24), payload=json.dumps({"public_id": order.public_id}),
            )
            self.db.add(payment)
            self.db.flush()
        self.db.add(models.PaymentTransaction(
            payment_id=payment.id, kind="create", provider=provider_name, amount=payment.amount, raw="{}"))
        self.db.commit()
        action = provider.create_payment(payment, order, return_url)
        log.info("payment created id=%s order=%s provider=%s", payment.id, order.id, provider_name)
        return payment, action

    def _pay_with_wallet(self, order: models.Order) -> tuple[models.Payment, dict]:
        from app.services import wallet as wallet_svc
        payment = models.Payment(
            order_id=order.id, provider="wallet", status="PENDING",
            amount=q(order.total), currency=order.currency, idempotency_key=new_token(24))
        self.db.add(payment)
        self.db.flush()
        try:
            wallet_svc.spend(self.db, order.user_id, order.total, reference=order.public_id)
        except Exception:
            payment.status = "FAILED"
            self.db.commit()
            raise PaymentError("insufficient_funds")
        payment.status = "PAID"
        import datetime as dt
        payment.paid_at = dt.datetime.utcnow()
        self.db.commit()
        order_svc.mark_paid(self.db, order, "wallet", payment.idempotency_key)
        return payment, {"action": "paid", "order": order.public_id}

    def handle_webhook(self, provider_name: str, data: dict, headers: dict) -> dict:
        """Verify -> locate payment -> idempotent PAID. Returns provider response."""
        provider = get_provider(provider_name)
        valid, _ = provider.verify_webhook(data, headers)
        if not valid:
            log.warning("webhook signature invalid provider=%s", provider_name)
            raise PaymentError("invalid_signature")
        parsed = provider.parse_webhook(data)
        payment = None
        ref = parsed.get("payment_db_id")
        if ref:
            try:
                payment = self.db.get(models.Payment, int(ref))
            except (ValueError, TypeError):
                payment = None
        if not payment and parsed.get("external_id"):
            payment = self.db.query(models.Payment).filter_by(
                provider=provider_name, external_id=parsed["external_id"]).first()
        if not payment:
            log.warning("webhook for unknown payment provider=%s", provider_name)
            raise PaymentError("payment_not_found")
        self.db.add(models.PaymentTransaction(
            payment_id=payment.id, kind="callback", provider=provider_name,
            external_id=parsed.get("external_id", ""), amount=q(parsed.get("amount", 0)),
            raw=json.dumps(data, default=str)[:4000]))
        if parsed.get("paid") and payment.status != "PAID":
            if q(parsed.get("amount", 0)) != q(payment.amount) and provider_name != "stars":
                payment.status = "FAILED"
                self.db.commit()
                raise PaymentError("amount_mismatch")
            payment.external_id = parsed.get("external_id", "") or payment.external_id
            payment.status = "PAID"
            import datetime as dt
            payment.paid_at = dt.datetime.utcnow()
            self.db.commit()
            order = self.db.get(models.Order, payment.order_id)
            if order:
                order_svc.mark_paid(self.db, order, provider_name, payment.external_id)
            log.info("payment PAID id=%s provider=%s", payment.id, provider_name)
        else:
            self.db.commit()
        return {"ok": True, "payment_id": payment.id, "status": payment.status}
