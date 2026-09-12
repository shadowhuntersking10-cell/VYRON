"""User orders & payment status API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import Order, Payment, User
from vyron.errors import ForbiddenError, NotFoundError, ValidationError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user
from vyron.services import order_service, payment_service
from vyron.web.serializers import order_public, payment_public

router = APIRouter(prefix="/api", tags=["orders"])


def _own_order(db: DbSession, user: User, order_id: str) -> Order:
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id, Order.user_id == user.id).first()
    if order is None:
        raise NotFoundError("Order not found.")
    return order


@router.get("/orders")
def list_orders(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    query = db.query(Order).options(joinedload(Order.items)).filter(Order.user_id == user.id)
    if status:
        query = query.filter(Order.status == status.upper())
    total = query.count()
    orders = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([order_public(o) for o in orders], total, page, page_size)


def _latest_payment(db: DbSession, order: Order) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.order_id == order.id)
        .order_by(Payment.created_at.desc())
        .first()
    )


@router.get("/orders/{order_id}")
def get_order(order_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = _own_order(db, user, order_id)
    data = order_public(order)
    payment = _latest_payment(db, order)
    data["payment"] = payment_public(payment) if payment else None
    return ok(data)


@router.get("/orders/{order_id}/status")
def order_status(order_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    order = _own_order(db, user, order_id)
    return ok(
        {
            "status": order.status,
            "items": [{"id": item.id, "delivery_state": item.delivery_state} for item in order.items],
            "timeline": order_public(order)["timeline"],
        }
    )


@router.post("/orders/{order_id}/cancel")
def cancel_order(
    order_id: str,
    payload: Dict[str, Any] = Body(default={}),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    order = _own_order(db, user, order_id)
    order_service.cancel_order(db, order, actor_type="USER", actor_id=user.id, reason=str(payload.get("reason", ""))[:200] or "Cancelled by user")
    return ok(order_public(order), message_code="ORDER_CANCELLED")


@router.post("/orders/{order_id}/refund-request")
def request_refund(
    order_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "refund-request", "3/hour", user_id=user.id)
    order = _own_order(db, user, order_id)
    reason = str(payload.get("reason", "")).strip()
    if not reason:
        raise ValidationError("A refund reason is required.", code="REASON_REQUIRED")
    payment_service.request_order_refund(db, order, user, reason[:400])
    return ok(message_code="REFUND_REQUESTED")


@router.post("/orders/{order_id}/pay")
def pay_order(
    order_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Initiate (or resume) payment for an order: creates a PENDING payment with a
    provider checkout_url. Raises PAYMENT_PROVIDER_NOT_CONFIGURED when the chosen
    provider has no credentials — never falls back to a fake success."""
    from vyron.enums import OrderStatus, PaymentPurpose

    enforce_rate_limit(request, "order-pay", "10/minute", user_id=user.id)
    order = _own_order(db, user, order_id)
    if order.status not in (OrderStatus.CREATED.value, OrderStatus.PAYMENT_PENDING.value):
        raise ValidationError("This order can no longer be paid.", code="ORDER_NOT_PAYABLE")

    provider = str(payload.get("provider") or order.payment_provider or "").strip()
    if not provider:
        raise ValidationError("Choose a payment provider.", code="PROVIDER_REQUIRED")

    payment = payment_service.create_payment(
        db,
        purpose=PaymentPurpose.ORDER,
        amount=order.total,
        currency=order.currency,
        description=f"VYRON order {order.number}",
        user=user,
        provider_name=provider,
        order=order,
    )
    order.payment_provider = payment.provider
    if order.status == OrderStatus.CREATED.value:
        order_service.transition(
            db, order, OrderStatus.PAYMENT_PENDING,
            reason="payment_initiated", actor_type="USER", actor_id=user.id, commit=False,
        )
    db.commit()
    db.refresh(order)
    return ok(
        {"order": order_public(order), "payment": payment_public(payment)},
        message_code="PAYMENT_INITIATED",
    )


@router.post("/payments/{payment_id}/verify")
def verify_payment(
    payment_id: str,
    request: Request,
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Server-side status check against the provider (return from checkout)."""
    enforce_rate_limit(request, "payment-verify", "20/minute", user_id=user.id)
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if payment is None:
        raise NotFoundError("Payment not found.")
    owner_id = payment.user_id
    if owner_id is None and payment.order_id:
        order = db.get(Order, payment.order_id)
        owner_id = order.user_id if order else None
    if owner_id != user.id:
        raise ForbiddenError()
    payment = payment_service.verify_payment_status(db, payment.id)
    return ok(payment_public(payment))
