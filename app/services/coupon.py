"""Coupon validation and discount calculation (server-side)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.services.pricing import q


def validate(db: Session, code: str, user_id: int | None, subtotal,
             game_id: int | None = None, product_id: int | None = None) -> tuple[models.Coupon | None, Decimal, str]:
    """Returns (coupon, discount_amount, error_key)."""
    code = (code or "").strip().upper()
    if not code:
        return None, Decimal("0"), ""
    subtotal = q(subtotal)
    coupon = db.query(models.Coupon).filter_by(code=code, is_active=True).first()
    if not coupon:
        return None, Decimal("0"), "coupon_invalid"
    now = dt.datetime.utcnow()
    if coupon.expires_at and coupon.expires_at < now:
        return None, Decimal("0"), "coupon_expired"
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        return None, Decimal("0"), "coupon_exhausted"
    if subtotal < q(coupon.min_order):
        return None, Decimal("0"), "coupon_min_order"
    if coupon.game_id and coupon.game_id != game_id:
        return None, Decimal("0"), "coupon_not_applicable"
    if coupon.product_id and coupon.product_id != product_id:
        return None, Decimal("0"), "coupon_not_applicable"
    if user_id and coupon.per_user_limit:
        used = db.query(models.CouponUsage).filter_by(coupon_id=coupon.id, user_id=user_id).count()
        if used >= coupon.per_user_limit:
            return None, Decimal("0"), "coupon_limit_reached"
    if coupon.kind == "percent":
        discount = (subtotal * q(coupon.value) / 100).quantize(Decimal("0.01"))
    else:
        discount = min(subtotal, q(coupon.value))
    return coupon, discount, ""


def consume(db: Session, coupon: models.Coupon, user_id: int, order_id: int, amount) -> None:
    coupon.used_count = (coupon.used_count or 0) + 1
    db.add(models.CouponUsage(coupon_id=coupon.id, user_id=user_id, order_id=order_id, amount=q(amount)))
    db.flush()
