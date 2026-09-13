from decimal import Decimal

import pytest

from app.models import PayoutStatus
from app.services import marketplace_service, payout_service
from tests.conftest import make_user


async def test_payout_flow(db):
    seller_user = await make_user(db, "ps@vyronmail.com")
    admin = await make_user(db, "pa@vyronmail.com")
    seller = await marketplace_service.become_seller(db, seller_user, "ShopP")
    bal = await marketplace_service.get_balance(db, seller.id)
    bal.available = Decimal("100.00")
    await db.commit()
    payout = await payout_service.request_payout(db, seller.id, Decimal(60), method="card", details={})
    await db.commit()
    assert payout.status == PayoutStatus.REQUESTED
    await payout_service.set_status(db, payout, PayoutStatus.COMPLETED, admin_id=admin.id)
    await db.commit()
    await db.refresh(bal)
    assert bal.available == Decimal("40.00")
    assert bal.pending == Decimal("0.00")


async def test_payout_insufficient_rejected(db):
    seller_user = await make_user(db, "ps2@vyronmail.com")
    seller = await marketplace_service.become_seller(db, seller_user, "ShopP2")
    with pytest.raises(ValueError):
        await payout_service.request_payout(db, seller.id, Decimal(10), method="card", details={})
