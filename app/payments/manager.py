"""PaymentManager: registry + idempotent payment lifecycle over Order/Payment."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, Payment, PaymentStatus, PaymentTransaction
from app.payments.base import PaymentProvider, ProviderNotConfigured
from app.payments.click import ClickProvider
from app.payments.payme import PaymeProvider
from app.payments.stars_provider import StarsProvider
from app.payments.stripe_provider import StripeProvider
from app.utils.helpers import utcnow


class PaymentManager:
    def __init__(self) -> None:
        self._providers: dict[str, PaymentProvider] = {
            "payme": PaymeProvider(),
            "click": ClickProvider(),
            "stripe": StripeProvider(),
            "stars": StarsProvider(),
        }

    def providers(self) -> dict[str, PaymentProvider]:
        return dict(self._providers)

    def get(self, name: str) -> PaymentProvider:
        provider = self._providers.get((name or "").lower())
        if not provider:
            raise ValueError(f"unknown_provider:{name}")
        return provider

    def status_list(self) -> list[dict]:
        return [{"name": n, "configured": p.configured} for n, p in self._providers.items()]

    async def init_payment(
        self,
        db: AsyncSession,
        order: Order,
        provider_name: str,
        *,
        return_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> Payment:
        provider = self.get(provider_name)
        provider.require_configured()
        key = idempotency_key or f"pay-{order.public_id}-{uuid.uuid4().hex[:8]}"
        existing = (await db.execute(select(Payment).where(Payment.idempotency_key == key))).scalars().first()
        if existing:
            return existing

        result = await provider.create_payment(
            amount=order.total, currency=order.currency,
            order_public_id=order.public_id, return_url=return_url,
        )
        payment = Payment(
            order_id=order.id, user_id=order.user_id, provider=provider.name,
            provider_payment_id=result.provider_payment_id, status=PaymentStatus.PENDING,
            amount=order.total, currency=order.currency, idempotency_key=key,
            checkout_url=result.checkout_url, raw_init=result.raw,
        )
        db.add(payment)
        await db.flush()
        db.add(PaymentTransaction(payment_id=payment.id, kind="init", status="PENDING", payload=result.raw))
        order.timeline = (order.timeline or []) + [{"event": "payment_started", "provider": provider.name, "at": utcnow().isoformat()}]
        await db.flush()
        return payment

    async def init_wallet_topup(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        amount,
        currency: str,
        provider_name: str,
        return_url: str | None = None,
    ) -> Payment:
        """Wallet deposit: a Payment without an order. Webhook settlement credits the wallet."""
        from decimal import Decimal as _D

        provider = self.get(provider_name)
        provider.require_configured()
        if _D(str(amount)) <= 0:
            raise ValueError("bad_amount")
        ref = f"WALLET-{user_id}-{uuid.uuid4().hex[:10]}"
        result = await provider.create_payment(
            amount=_D(str(amount)), currency=currency, order_public_id=ref, return_url=return_url,
        )
        payment = Payment(
            order_id=None, user_id=user_id, provider=provider.name,
            provider_payment_id=result.provider_payment_id or ref, status=PaymentStatus.PENDING,
            amount=_D(str(amount)), currency=currency,
            idempotency_key=f"wtop-{ref}",
            checkout_url=result.checkout_url,
            raw_init={**(result.raw or {}), "wallet_topup": True, "ref": ref},
        )
        db.add(payment)
        await db.flush()
        db.add(PaymentTransaction(payment_id=payment.id, kind="init", status="PENDING",
                                  payload={"wallet_topup": True, "ref": ref}))
        await db.flush()
        return payment

    async def mark_paid(
        self, db: AsyncSession, payment: Payment, *, provider_payment_id: str | None = None, payload: dict | None = None
    ) -> Payment:
        """Idempotent: repeated calls are safe."""
        if payment.status == PaymentStatus.PAID:
            return payment
        payment.status = PaymentStatus.PAID
        payment.paid_at = utcnow()
        if provider_payment_id:
            payment.provider_payment_id = provider_payment_id
        db.add(PaymentTransaction(payment_id=payment.id, kind="webhook", status="PAID", payload=payload, signature_valid=True))
        order = await db.get(Order, payment.order_id) if payment.order_id else None
        if order and order.status == OrderStatus.PENDING_PAYMENT:
            order.status = OrderStatus.PAID
            order.timeline = (order.timeline or []) + [{"event": "payment_confirmed", "at": utcnow().isoformat()}]
            from app.services.notification_service import notify_order_event as _notify

            await _notify(db, user_id=order.user_id, title="Payment confirmed ✅",
                          body=f"{order.public_id} · {payment.amount} {payment.currency} via {payment.provider}.",
                          link=f"/app/orders/{order.public_id}")
        await db.flush()
        return payment

    async def mark_failed(self, db: AsyncSession, payment: Payment, *, error: str, payload: dict | None = None) -> Payment:
        if payment.status in (PaymentStatus.PAID, PaymentStatus.REFUNDED):
            return payment
        payment.status = PaymentStatus.FAILED
        db.add(PaymentTransaction(payment_id=payment.id, kind="webhook", status="FAILED", payload={**(payload or {}), "error": error}))
        await db.flush()
        return payment


_manager: PaymentManager | None = None


def get_payment_manager() -> PaymentManager:
    global _manager
    if _manager is None:
        _manager = PaymentManager()
    return _manager
