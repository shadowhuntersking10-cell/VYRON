"""Coupon validation & redemption — race-condition safe.

Validation happens AGAINST SERVER STATE at checkout time (never trusting the
frontend). Redemption locks the coupon row (SELECT ... FOR UPDATE), re-checks
limits and increments usage inside the order transaction; the unique
(coupon_id, order_id) constraint is the final guard.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import Coupon, CouponRedemption, Product, ProductVariant, User
from vyron.enums import CouponType
from vyron.errors import CouponError
from vyron.money import pct_of, to_money


def find_coupon(db: DbSession, code: str) -> Optional[Coupon]:
    return db.query(Coupon).filter(Coupon.code == (code or "").strip().upper()).first()


def validate_coupon(
    db: DbSession,
    coupon: Coupon,
    user: User,
    subtotal: Decimal,
    items: List[Tuple[ProductVariant, int]],
) -> Decimal:
    """Validate all rules and return the exact discount amount."""
    now = utcnow()
    if not coupon.active:
        raise CouponError("This coupon is no longer active.", code="COUPON_INACTIVE")
    if coupon.starts_at and coupon.starts_at > now:
        raise CouponError("This coupon is not active yet.", code="COUPON_NOT_STARTED")
    if coupon.expires_at and coupon.expires_at < now:
        raise CouponError("This coupon has expired.", code="COUPON_EXPIRED")
    if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
        raise CouponError("This coupon has reached its usage limit.", code="COUPON_EXHAUSTED")

    user_uses = (
        db.query(CouponRedemption)
        .filter(CouponRedemption.coupon_id == coupon.id, CouponRedemption.user_id == user.id)
        .count()
    )
    if user_uses >= max(1, coupon.per_user_limit):
        raise CouponError("You have already used this coupon.", code="COUPON_USER_LIMIT")

    if coupon.min_order_amount is not None and subtotal < to_money(coupon.min_order_amount):
        raise CouponError(
            f"Minimum order amount for this coupon is {coupon.min_order_amount}.", code="COUPON_MIN_ORDER"
        )

    if coupon.user_ids:
        if user.id not in [str(uid) for uid in coupon.user_ids]:
            raise CouponError("This coupon is not available for your account.", code="COUPON_USER_RESTRICTED")

    if coupon.game_ids or coupon.product_ids:
        game_ids = {str(g) for g in (coupon.game_ids or [])}
        product_ids = {str(p) for p in (coupon.product_ids or [])}
        matched = False
        for variant, _qty in items:
            product = db.get(Product, variant.product_id)
            if product is None:
                continue
            if product_ids and product.id in product_ids:
                matched = True
                break
            if game_ids and product.game_id and product.game_id in game_ids:
                matched = True
                break
        if not matched:
            raise CouponError("This coupon does not apply to the products in your order.", code="COUPON_PRODUCT_RESTRICTED")

    if coupon.type == CouponType.PERCENTAGE.value:
        discount = pct_of(subtotal, coupon.value)
        if coupon.max_discount is not None:
            discount = min(discount, to_money(coupon.max_discount))
    else:
        discount = min(to_money(coupon.value), subtotal)
    return to_money(discount)


def redeem_coupon(db: DbSession, coupon: Coupon, user: User, order_id: str, discount: Decimal) -> CouponRedemption:
    """Locks the coupon row, re-verifies limits and records the redemption.
    Must run inside the order creation transaction (no separate commit)."""
    locked: Optional[Coupon] = db.query(Coupon).with_for_update().filter(Coupon.id == coupon.id).first()
    if locked is None or not locked.active:
        raise CouponError("This coupon is no longer available.", code="COUPON_INACTIVE")
    if locked.max_uses is not None and locked.used_count >= locked.max_uses:
        raise CouponError("This coupon has reached its usage limit.", code="COUPON_EXHAUSTED")
    locked.used_count = (locked.used_count or 0) + 1
    redemption = CouponRedemption(coupon_id=locked.id, user_id=user.id, order_id=order_id, discount=discount)
    db.add(redemption)
    db.flush()
    return redemption


# --- admin management ------------------------------------------------------------------
def _parse_dt(value):
    if not value:
        return None
    from datetime import datetime

    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _apply_coupon_fields(coupon: Coupon, payload: dict) -> Coupon:
    if "code" in payload and payload["code"]:
        coupon.code = str(payload["code"]).strip().upper()[:40]
    if "type" in payload and payload["type"]:
        coupon.type = str(payload["type"]).upper()
        if coupon.type not in {t.value for t in CouponType}:
            raise CouponError("Invalid coupon type.", code="COUPON_TYPE_INVALID")
    if "value" in payload and payload["value"] is not None:
        coupon.value = to_money(payload["value"])
    if "currency" in payload and payload["currency"]:
        coupon.currency = str(payload["currency"]).upper()[:8]
    if "max_discount" in payload:
        coupon.max_discount = to_money(payload["max_discount"]) if payload["max_discount"] not in (None, "") else None
    if "max_uses" in payload:
        coupon.max_uses = int(payload["max_uses"]) if payload["max_uses"] not in (None, "") else None
    if "per_user_limit" in payload:
        coupon.per_user_limit = int(payload["per_user_limit"]) if payload["per_user_limit"] not in (None, "") else None
    if "min_order_amount" in payload:
        coupon.min_order_amount = to_money(payload["min_order_amount"]) if payload["min_order_amount"] not in (None, "") else None
    if "game_ids" in payload:
        coupon.game_ids = [str(g) for g in (payload["game_ids"] or [])] or None
    if "product_ids" in payload:
        coupon.product_ids = [str(p) for p in (payload["product_ids"] or [])] or None
    if "starts_at" in payload:
        coupon.starts_at = _parse_dt(payload["starts_at"])
    if "expires_at" in payload:
        coupon.expires_at = _parse_dt(payload["expires_at"])
    if "active" in payload:
        coupon.active = bool(payload["active"])
    return coupon


def admin_create_coupon(db: DbSession, admin: User, payload: dict) -> Coupon:
    code = str(payload.get("code", "")).strip().upper()
    if len(code) < 3:
        raise CouponError("Coupon code must be at least 3 characters.", code="COUPON_CODE_INVALID")
    if find_coupon(db, code) is not None:
        raise CouponError("This coupon code already exists.", code="COUPON_EXISTS")
    coupon = Coupon(code=code, created_by=admin.id)
    _apply_coupon_fields(coupon, payload)
    if coupon.type is None or coupon.value is None:
        raise CouponError("Type and value are required.", code="COUPON_FIELDS_REQUIRED")
    db.add(coupon)
    db.commit()
    from vyron.services import audit_service

    audit_service.record_admin_action(db, admin, "coupon.created", target_type="coupon", target_id=coupon.id, data={"code": coupon.code})
    return coupon


def admin_update_coupon(db: DbSession, admin: User, coupon: Coupon, payload: dict) -> Coupon:
    new_code = str(payload.get("code", "")).strip().upper()
    if new_code and new_code != coupon.code:
        if find_coupon(db, new_code) is not None:
            raise CouponError("This coupon code already exists.", code="COUPON_EXISTS")
    _apply_coupon_fields(coupon, payload)
    db.commit()
    from vyron.services import audit_service

    audit_service.record_admin_action(db, admin, "coupon.updated", target_type="coupon", target_id=coupon.id, data={"code": coupon.code})
    return coupon
