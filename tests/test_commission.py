from decimal import Decimal

from app.models import MarketplaceListing, Order, OrderItem, OrderStatus
from app.services import marketplace_service
from app.utils.helpers import generate_public_id, utcnow
from tests.conftest import make_user


async def _market_order(db, buyer_id, listing, total=Decimal(100)):
    order = Order(public_id=generate_public_id(), user_id=buyer_id, status=OrderStatus.PAID,
                  idempotency_key=generate_public_id("t"), subtotal=total, total=total,
                  timeline=[{"event": "order_created", "at": utcnow().isoformat()}])
    db.add(order)
    await db.flush()
    db.add(OrderItem(order_id=order.id, kind="marketplace", listing_id=listing.id,
                     title=listing.title, quantity=1, unit_price=total, total_price=total))
    await db.commit()
    return order


async def test_default_commission_split(db):
    seller_user = await make_user(db, "cs@vyronmail.com")
    buyer = await make_user(db, "cb@vyronmail.com")
    seller = await marketplace_service.become_seller(db, seller_user, "Shop")
    listing = MarketplaceListing(seller_id=seller.id, title="Item", price=Decimal(100), status="active")
    db.add(listing)
    await db.commit()
    order = await _market_order(db, buyer.id, listing)
    await marketplace_service.settle_marketplace_order(db, order)
    await db.commit()
    bal = await marketplace_service.get_balance(db, seller.id)
    # default 10%: seller 90, platform 10
    assert bal.available == Decimal("90.00")
    assert bal.lifetime_earned == Decimal("90.00")


async def test_seller_override_commission(db):
    seller_user = await make_user(db, "cs2@vyronmail.com")
    buyer = await make_user(db, "cb2@vyronmail.com")
    seller = await marketplace_service.become_seller(db, seller_user, "Shop2")
    seller.commission_percent = Decimal(0)
    await db.commit()
    listing = MarketplaceListing(seller_id=seller.id, title="Item2", price=Decimal(50), status="active")
    db.add(listing)
    await db.commit()
    order = await _market_order(db, buyer.id, listing, total=Decimal(50))
    await marketplace_service.settle_marketplace_order(db, order)
    await db.commit()
    bal = await marketplace_service.get_balance(db, seller.id)
    assert bal.available == Decimal("50.00")
