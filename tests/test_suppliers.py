from decimal import Decimal

import pytest

from app.models import OrderStatus
from app.orders.processor import get_order_processor
from app.services import checkout_service
from app.suppliers.base import SupplierNotConfigured
from app.suppliers.generic import GenericSupplier
from app.suppliers.manual import ManualSupplier
from tests.conftest import make_catalog, make_user


async def test_manual_supplier_always_available():
    m = ManualSupplier()
    assert m.configured
    res = await m.create_order(external_product_id="x", customer_fields={})
    assert res.ok and res.status == "QUEUED"


async def test_generic_unconfigured_raises():
    g = GenericSupplier()
    assert not g.configured
    with pytest.raises(SupplierNotConfigured):
        await g.create_order(external_product_id="x", customer_fields={})


async def test_manual_order_goes_to_review(db):
    u = await make_user(db, "sup@vyronmail.com")
    _, _, p = await make_catalog(db)
    order = await checkout_service.create_order(db, user_id=u.id, product_id=p.id)
    order.status = OrderStatus.PAID
    await db.commit()
    await get_order_processor().on_payment_confirmed(db, order)
    await db.refresh(order)
    assert order.status == OrderStatus.MANUAL_REVIEW
    assert len(order.timeline) >= 2
