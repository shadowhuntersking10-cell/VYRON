"""Checkout API — cart checkout, buy-now, available providers."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.db.models import Order, Payment, User
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user
from vyron.security.sessions import client_ip
from vyron.services import cart_service, order_service, payment_service
from vyron.web.serializers import cart_payload, order_public, payment_public

router = APIRouter(prefix="/api", tags=["checkout"])


def _latest_payment(db: DbSession, order: Order) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.order_id == order.id)
        .order_by(Payment.created_at.desc())
        .first()
    )


@router.get("/payment-providers")
def providers(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(payment_service.available_providers(db))


@router.get("/checkout/summary")
def summary(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    calc = cart_service.calculate(db, user)
    return ok(cart_payload(calc)["totals"])


@router.post("/checkout")
def checkout(
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "checkout", "10/minute", user_id=user.id)
    idem = str(
        payload.get("idempotency_key")
        or request.headers.get("idempotency-key")
        or ""
    )[:80] or None
    # NOTE: no cart pre-check here — create_order_from_cart replays an existing
    # order for the same idempotency key BEFORE validating the (now empty) cart,
    # so a double-click/duplicate submit returns the original order.
    order = order_service.create_order_from_cart(
        db,
        user,
        provider_name=payload.get("provider"),
        idempotency_key=idem,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        coupon_code=payload.get("coupon_code"),
    )
    payment = _latest_payment(db, order)
    return ok(
        {"order": order_public(order), "payment": payment_public(payment) if payment else None},
        message_code="ORDER_CREATED",
    )


@router.post("/checkout/buy-now")
def buy_now(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "buynow", "10/minute", user_id=user.id)
    idem = str(
        payload.get("idempotency_key")
        or request.headers.get("idempotency-key")
        or ""
    )[:80] or None
    order = order_service.create_direct_order(
        db,
        user,
        variant_id=str(payload.get("variant_id", "")),
        quantity=int(payload.get("quantity", 1)),
        required_field_values=payload.get("required_field_values") or payload.get("topup_fields") or {},
        provider_name=payload.get("provider"),
        idempotency_key=idem,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    payment = _latest_payment(db, order)
    return ok(
        {"order": order_public(order), "payment": payment_public(payment) if payment else None},
        message_code="ORDER_CREATED",
    )
