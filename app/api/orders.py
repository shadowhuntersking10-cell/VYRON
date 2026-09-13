"""Checkout + orders API. Totals always recalculated server-side."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app import models
from app.config import settings
from app.dependencies import Db, require_user
from app.payments.service import PaymentError, PaymentService
from app.schemas import CheckoutIn
from app.services import orders as order_svc

router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/checkout")
def checkout(body: CheckoutIn, request: Request, db: Db):
    user = require_user(request, db)
    if not settings.SALES_ENABLED:
        raise HTTPException(status_code=403, detail="sales_disabled")
    kind = "topup"
    items = [i.model_dump() for i in body.items]
    if any(i.get("listing_id") for i in items):
        kind = "marketplace"
    try:
        order = order_svc.create_order(
            db, user, items, coupon_code=body.coupon_code,
            customer_fields=body.customer_fields,
            idempotency_key=body.idempotency_key, kind=kind)
    except order_svc.OrderError as e:
        raise HTTPException(status_code=400, detail=e.key)
    # create payment
    try:
        payment, action = PaymentService(db).create_for_order(
            order, body.provider, return_url=f"{settings.BASE_URL}/orders/{order.public_id}")
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return {"order": {"public_id": order.public_id, "status": order.status,
                      "total": str(order.total), "currency": order.currency,
                      "discount": str(order.discount)},
            "payment": {"id": payment.id, "provider": payment.provider, "status": payment.status},
            "action": action}


@router.post("/orders/{public_id}/pay")
def pay_order(public_id: str, request: Request, db: Db, provider: str = "payme"):
    user = require_user(request, db)
    order = db.query(models.Order).filter_by(public_id=public_id, user_id=user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    if order.status != "PENDING_PAYMENT":
        raise HTTPException(status_code=400, detail="order_not_payable")
    try:
        payment, action = PaymentService(db).create_for_order(
            order, provider, return_url=f"{settings.BASE_URL}/orders/{order.public_id}")
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return {"payment": {"id": payment.id, "status": payment.status}, "action": action}


@router.get("/orders")
def my_orders(request: Request, db: Db, page: int = 1, per_page: int = 20):
    user = require_user(request, db)
    q = db.query(models.Order).filter_by(user_id=user.id).order_by(models.Order.id.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"public_id": o.public_id, "status": o.status, "total": str(o.total),
                       "currency": o.currency, "kind": o.kind,
                       "created_at": o.created_at.isoformat()} for o in items],
            "total": total}


@router.get("/orders/{public_id}")
def order_detail(public_id: str, request: Request, db: Db):
    user = require_user(request, db)
    order = db.query(models.Order).filter_by(public_id=public_id, user_id=user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    import json
    try:
        timeline = json.loads(order.timeline or "[]")
    except Exception:
        timeline = []
    return {"public_id": order.public_id, "status": order.status, "kind": order.kind,
            "subtotal": str(order.subtotal), "discount": str(order.discount),
            "service_fee": str(order.service_fee), "payment_fee": str(order.payment_fee),
            "total": str(order.total), "currency": order.currency,
            "items": [{"title": i.title, "qty": i.quantity, "unit": str(i.unit_price),
                       "total": str(i.total_price)} for i in order.items],
            "timeline": timeline}
