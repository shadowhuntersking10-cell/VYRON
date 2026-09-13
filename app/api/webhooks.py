"""Secure payment webhooks: signature verification + idempotent processing."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Order, Payment, PaymentStatus
from app.orders.processor import get_order_processor
from app.payments.base import ProviderNotConfigured
from app.payments.manager import get_payment_manager
from app.payments.stripe_provider import StripeProvider

log = logging.getLogger("vyron.webhooks")
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _settle_paid(db: AsyncSession, payment: Payment, provider_payment_id: str | None, payload: dict) -> None:
    manager = get_payment_manager()
    await manager.mark_paid(db, payment, provider_payment_id=provider_payment_id, payload=payload)
    await db.commit()
    # Wallet top-up (no order attached): credit the wallet ledger.
    if payment.order_id is None and (payment.raw_init or {}).get("wallet_topup"):
        from app.services import wallet_service
        from app.services.notification_service import notify_user as _notify

        wallet = await wallet_service.get_or_create_wallet(db, payment.user_id or 0)
        await wallet_service.credit(db, wallet, payment.amount, kind="topup",
                                    reference=f"pay:{payment.id}:{payment.provider}")
        await db.commit()
        if payment.user_id:
            # fresh session state for notify
            await _notify(db, user_id=payment.user_id, kind="payment", title="Wallet topped up",
                          body=f"{payment.amount} {payment.currency} added to your wallet.", link="/app/wallet")
            await db.commit()
        log.info("wallet top-up settled: user=%s amount=%s", payment.user_id, payment.amount)
        return
    order = await db.get(Order, payment.order_id) if payment.order_id else None
    if order:
        try:
            await get_order_processor().on_payment_confirmed(db, order)
        except Exception:  # noqa: BLE001 - worker safety net will retry
            log.exception("on_payment_confirmed failed for %s", order.public_id)


@router.post("/payme")
async def payme_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.json()
    provider = get_payment_manager().get("payme")
    try:
        result = await provider.handle_webhook(payload, dict(request.headers))
    except ProviderNotConfigured:
        return {"error": "provider_not_configured"}
    if not result.ok:
        return {"error": result.error or "bad_signature"}
    payment = (await db.execute(
        select(Payment).where(Payment.provider_payment_id == result.provider_payment_id, Payment.provider == "payme")
    )).scalars().first()
    if not payment and result.provider_payment_id:
        # Payme sends our order public id as merchant_trans_id
        order = (await db.execute(select(Order).where(Order.public_id == result.provider_payment_id))).scalars().first()
        if order and order.payments:
            payment = order.payments[0]
    if not payment:
        return {"error": "payment_not_found"}
    if result.status == "PAID":
        await _settle_paid(db, payment, result.provider_payment_id, payload)
        return {"result": {"receipt": result.provider_payment_id}}
    return {"result": {"status": result.status}}


@router.post("/click")
async def click_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    if "application/json" in (request.headers.get("content-type") or ""):
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    provider = get_payment_manager().get("click")
    try:
        result = await provider.handle_webhook(payload, dict(request.headers))
    except ProviderNotConfigured:
        return {"error": "-1", "error_note": "provider_not_configured"}
    if not result.ok:
        return {"error": "-1", "error_note": result.error}
    payment = None
    if result.provider_payment_id:
        order = (await db.execute(select(Order).where(Order.public_id == result.provider_payment_id))).scalars().first()
        if order:
            await db.refresh(order, attribute_names=["payments"])
            payment = order.payments[0] if order.payments else None
    if not payment:
        return {"error": "-5", "error_note": "payment_not_found"}
    if result.status == "PAID":
        await _settle_paid(db, payment, str(payload.get("click_trans_id") or payment.provider_payment_id), payload)
    return {"error": "0", "error_note": "Success"}


@router.post("/stripe")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    provider = get_payment_manager().get("stripe")
    assert isinstance(provider, StripeProvider)
    sig = request.headers.get("stripe-signature", "")
    if provider.configured and provider.webhook_secret and not provider.verify_signature(raw, sig):
        return {"error": "bad_signature"}
    import json as _json

    try:
        payload = _json.loads(raw or b"{}")
    except Exception:
        return {"error": "bad_payload"}
    try:
        result = await provider.handle_webhook(payload, dict(request.headers))
    except ProviderNotConfigured:
        return {"error": "provider_not_configured"}
    if result.provider_payment_id:
        payment = (await db.execute(select(Payment).where(
            Payment.provider_payment_id == result.provider_payment_id, Payment.provider == "stripe"
        ))).scalars().first()
        if payment and result.status == "PAID":
            await _settle_paid(db, payment, result.provider_payment_id, payload)
    return {"received": True}
