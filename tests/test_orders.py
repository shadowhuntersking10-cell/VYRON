from app.models import Order, OrderStatus
from app.services import checkout_service
from tests.conftest import make_catalog, make_user


async def test_quote_math_server_side(db):
    u = await make_user(db, "o1@vyronmail.com")
    _, _, p = await make_catalog(db)
    q = await checkout_service.quote(db, product_id=p.id, quantity=2, user_id=u.id)
    assert q["subtotal"] == 200
    assert q["total"] >= 200  # fees only add


async def test_create_order_idempotent(db):
    u = await make_user(db, "o2@vyronmail.com")
    _, _, p = await make_catalog(db)
    o1 = await checkout_service.create_order(db, user_id=u.id, product_id=p.id, idempotency_key="k-123")
    await db.commit()
    o2 = await checkout_service.create_order(db, user_id=u.id, product_id=p.id, idempotency_key="k-123")
    await db.commit()
    assert o1.id == o2.id
    assert o1.status == OrderStatus.PENDING_PAYMENT


async def test_missing_product_rejected(db):
    u = await make_user(db, "o3@vyronmail.com")
    try:
        await checkout_service.quote(db, product_id=999999, user_id=u.id)
        raise AssertionError("should have raised")
    except checkout_service.CheckoutError:
        pass
