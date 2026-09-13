from app.models import OrderStatus, RevenueLedger
from app.services import checkout_service, revenue_service
from sqlalchemy import select
from tests.conftest import make_catalog, make_user


async def test_revenue_only_for_completed(db):
    u = await make_user(db, "rev@vyronmail.com")
    _, _, p = await make_catalog(db)
    order = await checkout_service.create_order(db, user_id=u.id, product_id=p.id)
    await db.commit()
    assert await revenue_service.record_order_revenue(db, order) is None
    order.status = OrderStatus.COMPLETED
    entry = await revenue_service.record_order_revenue(db, order)
    await db.commit()
    assert entry is not None
    # idempotent
    again = await revenue_service.record_order_revenue(db, order)
    assert again.id == entry.id


async def test_revenue_summary(db):
    summary = await revenue_service.revenue_summary(db)
    assert "by_stream" in summary and "total_net" in summary
