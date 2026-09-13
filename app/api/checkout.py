"""Checkout: quote (server-calculated) -> create order -> init payment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_optional
from app.models import User
from app.payments.base import ProviderNotConfigured
from app.payments.manager import get_payment_manager
from app.schemas import CheckoutQuoteIn, CheckoutQuoteOut, OrderCreateIn, OrderOut, PaymentOut
from app.services import checkout_service

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("/quote", response_model=CheckoutQuoteOut)
async def quote(data: CheckoutQuoteIn, db: AsyncSession = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    try:
        q = await checkout_service.quote(
            db, product_id=data.product_id, variant_id=data.variant_id,
            listing_id=data.listing_id, quantity=data.quantity,
            coupon_code=data.coupon_code, user_id=user.id if user else None,
            customer_fields=data.customer_fields,
        )
    except checkout_service.CheckoutError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CheckoutQuoteOut(
        title=q["title"], unit_price=q["unit_price"], quantity=q["quantity"],
        subtotal=q["subtotal"], discount=q["discount"], service_fee=q["service_fee"],
        total=q["total"], currency=q["currency"], coupon_applied=q["coupon_applied"],
    )


@router.post("/orders", response_model=dict)
async def create_order(data: OrderCreateIn, db: AsyncSession = Depends(get_db), user: User | None = Depends(get_current_user_optional)):
    try:
        order = await checkout_service.create_order(
            db, user_id=user.id if user else None, product_id=data.product_id,
            variant_id=data.variant_id, listing_id=data.listing_id, quantity=data.quantity,
            coupon_code=data.coupon_code, customer_fields=data.customer_fields,
            idempotency_key=data.idempotency_key,
        )
        await db.commit()
    except checkout_service.CheckoutError as exc:
        raise HTTPException(400, str(exc)) from exc

    payments = get_payment_manager()
    try:
        payment = await payments.init_payment(db, order, data.provider)
        await db.commit()
    except ProviderNotConfigured:
        await db.commit()
        return {
            "order": OrderOut.model_validate(order).model_dump(),
            "payment": None,
            "error": "payment_provider_not_configured",
            "providers": payments.status_list(),
        }
    except Exception as exc:  # noqa: BLE001
        await db.commit()
        raise HTTPException(502, f"payment_init_failed:{exc}") from exc
    return {
        "order": OrderOut.model_validate(order).model_dump(),
        "payment": PaymentOut.model_validate(payment).model_dump(),
    }
