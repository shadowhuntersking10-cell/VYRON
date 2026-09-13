"""Coupon validation + application (server-side only)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Coupon, CouponUsage
from app.utils.money import D, money_percent, quantize_money


class CouponError(ValueError):
    pass


def _as_aware(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


async def validate_coupon(
    db: AsyncSession,
    code: str,
    *,
    user_id: int | None,
    subtotal: Decimal | float | int,
    game_id: int | None = None,
    product_id: int | None = None,
) -> tuple[Coupon, Decimal]:
    """Returns (coupon, discount_amount) or raises CouponError."""
    code = (code or "").strip().upper()
    if not code:
        raise CouponError("empty_code")
    coupon = (await db.execute(select(Coupon).where(Coupon.code == code))).scalars().first()
    if not coupon or not coupon.is_active:
        raise CouponError("invalid_coupon")
    now = dt.datetime.now(dt.timezone.utc)
    if _as_aware(coupon.starts_at) and now < _as_aware(coupon.starts_at):  # type: ignore[operator]
        raise CouponError("coupon_not_started")
    if _as_aware(coupon.expires_at) and now > _as_aware(coupon.expires_at):  # type: ignore[operator]
        raise CouponError("coupon_expired")
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        raise CouponError("coupon_exhausted")
    if coupon.game_id and coupon.game_id != game_id:
        raise CouponError("coupon_game_mismatch")
    if coupon.product_id and coupon.product_id != product_id:
        raise CouponError("coupon_product_mismatch")
    if D(subtotal) < D(coupon.min_order):
        raise CouponError("coupon_min_order")
    if user_id and coupon.per_user_limit > 0:
        used = (
            await db.execute(
                select(func.count())
                .select_from(CouponUsage)
                .where(CouponUsage.coupon_id == coupon.id, CouponUsage.user_id == user_id)
            )
        ).scalar() or 0
        if used >= coupon.per_user_limit:
            raise CouponError("coupon_user_limit")

    if coupon.kind == "percent":
        discount = money_percent(subtotal, coupon.value)
    else:
        discount = quantize_money(min(D(coupon.value), D(subtotal)))
    return coupon, discount


async def record_usage(db: AsyncSession, coupon: Coupon, *, user_id: int | None, order_id: int | None) -> None:
    coupon.used_count = (coupon.used_count or 0) + 1
    db.add(CouponUsage(coupon_id=coupon.id, user_id=user_id, order_id=order_id))
    await db.flush()
