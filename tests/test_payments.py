from decimal import Decimal

import pytest

from app.models import OrderStatus
from app.payments.base import ProviderNotConfigured
from app.payments.manager import PaymentManager
from app.services import checkout_service
from tests.conftest import make_catalog, make_user


async def test_unconfigured_provider_raises():
    mgr = PaymentManager()
    # no credentials in test env -> must raise, never fake success
    with pytest.raises(ProviderNotConfigured):
        await mgr.get("payme").create_payment(amount=Decimal(100), currency="UZS", order_public_id="X")
    with pytest.raises(ProviderNotConfigured):
        await mgr.get("click").create_payment(amount=Decimal(100), currency="UZS", order_public_id="X")
    with pytest.raises(ProviderNotConfigured):
        await mgr.get("stripe").create_payment(amount=Decimal(100), currency="USD", order_public_id="X")


async def test_unknown_provider():
    with pytest.raises(ValueError):
        PaymentManager().get("nope")


async def test_checkout_order_without_payment_config(client, db):
    u = await make_user(db, "pay@vyronmail.com")
    _, _, p = await make_catalog(db)
    r = await client.post("/api/checkout/orders", json={"product_id": p.id, "provider": "payme"})
    assert r.status_code == 200
    data = r.json()
    assert data["error"] == "payment_provider_not_configured"
    assert data["order"]["status"] == "PENDING_PAYMENT"
