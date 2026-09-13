import datetime as dt
import uuid
from decimal import Decimal

import pytest

from app.models import Coupon
from app.services import coupon_service
from app.utils.helpers import utcnow
from tests.conftest import make_user


async def _coupon(db, code=None, **kw):
    c = Coupon(code=code or f"T{uuid.uuid4().hex[:8].upper()}", kind="percent", value=Decimal(10), **kw)
    db.add(c)
    await db.commit()
    return c


async def test_percent_coupon(db):
    u = await make_user(db, "c1@vyronmail.com")
    c = await _coupon(db)
    coupon, discount = await coupon_service.validate_coupon(db, c.code.lower(), user_id=u.id, subtotal=Decimal(1000))
    assert discount == Decimal("100.00")


async def test_expired_coupon_rejected(db):
    u = await make_user(db, "c2@vyronmail.com")
    c = await _coupon(db, expires_at=utcnow() - dt.timedelta(days=1))
    with pytest.raises(coupon_service.CouponError):
        await coupon_service.validate_coupon(db, c.code, user_id=u.id, subtotal=Decimal(1000))


async def test_min_order_enforced(db):
    u = await make_user(db, "c3@vyronmail.com")
    c = await _coupon(db, min_order=Decimal(5000))
    with pytest.raises(coupon_service.CouponError):
        await coupon_service.validate_coupon(db, c.code, user_id=u.id, subtotal=Decimal(100))
