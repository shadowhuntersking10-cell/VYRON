from decimal import Decimal

from app.models import OrderStatus
from tests.conftest import make_catalog, make_user


async def test_user_game_product_models(db):
    u = await make_user(db, "m@vyronmail.com")
    _, g, p = await make_catalog(db)
    assert u.id and g.id and p.id
    assert isinstance(p.selling_price, Decimal)


async def test_order_status_values():
    assert OrderStatus.COMPLETED.value == "COMPLETED"
    assert OrderStatus.MANUAL_REVIEW.value == "MANUAL_REVIEW"
