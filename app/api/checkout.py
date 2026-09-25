"""Checkout + order APIs (server-side pricing, payment architecture)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import pagination, require_user
from app.api.cart import get_cart, serialize_cart
from app.db import get_db
from app.models import Order, OrderStatus, Payment, PaymentStatus, User
from app.security import new_idempotency_key, rate_limit
from app.services.orders import CheckoutError, create_order_from_cart, serialize_order, store_full_player_info
from app.services.payments import PaymentError, create_payment_for_order

router = APIRouter(prefix="/api", tags=["checkout"])


class CheckoutBody(BaseModel):
    player_info: dict = Field(default_factory=dict)
    coupon_code: Optional[str] = None
    idempotency_key: Optional[str] = None


@router.post("/checkout")
async def checkout(
    body: CheckoutBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    if not rate_limit(f"checkout:{user.id}", 10, 60):
        raise HTTPException(status_code=429, detail="rate_limited")

    cart = get_cart(db, user)
    try:
        order = create_order_from_cart(
            db,
            user,
            cart,
            player_info=body.player_info,
            coupon_code=body.coupon_code or cart.coupon_code,
            idempotency_key=body.idempotency_key,
        )
    except CheckoutError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.key)

    store_full_player_info(order, body.player_info)
    if order.payments and order.payments[-1].status == PaymentStatus.PENDING:
        payment = order.payments[-1]
    else:
        try:
            payment = await create_payment_for_order(
                db,
                order,
                return_url=f"{request.base_url}orders/{order.order_number}",
                description=f"VYRON {order.order_number}",
            )
        except PaymentError as exc:
            # Honest state: order exists but payment is NOT configured.
            db.commit()
            return {
                "order": serialize_order(order),
                "payment": None,
                "error": exc.key,
                "checkout_url": None,
            }
    db.commit()
    return {
        "order": serialize_order(order),
        "payment": {
            "id": payment.id,
            "provider": payment.provider,
            "status": payment.status.value,
            "amount": payment.amount,
            "currency": payment.currency,
        },
        "checkout_url": payment.checkout_url,
        "error": None,
    }


@router.get("/orders")
def my_orders(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    query = select(Order).where(Order.user_id == user.id)
    if status:
        try:
            query = query.where(Order.status == OrderStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_status")
    from sqlalchemy import func

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar() or 0
    page, page_size = pagination(page, page_size)
    rows = (
        db.execute(
            query.order_by(Order.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [serialize_order(o) for o in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/orders/{order_number}")
def order_detail(
    order_number: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    order = db.execute(
        select(Order).where(Order.order_number == order_number)
    ).scalar_one_or_none()
    if order is None or (order.user_id != user.id and not user.is_staff):
        raise HTTPException(status_code=404, detail="order_not_found")
    return {"order": serialize_order(order, include_internal=user.is_staff)}
