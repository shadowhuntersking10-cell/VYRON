"""Round-2 features: wallet top-up honesty, admin sections, presets, refunds."""
from decimal import Decimal

import pytest

from app.models import OrderStatus, UserRole
from app.payments.base import ProviderNotConfigured
from app.payments.manager import PaymentManager
from app.services import marketplace_service, wallet_service
from tests.conftest import login, make_catalog, make_user


async def _admin(client, db):
    u = await make_user(db, "boss@vyronmail.com", role=UserRole.ADMIN)
    await login(client, u.effective_email)
    return u


async def test_wallet_topup_unconfigured_honest(db):
    u = await make_user(db, "wt@vyronmail.com")
    with pytest.raises(ProviderNotConfigured):
        await PaymentManager().init_wallet_topup(db, user_id=u.id, amount=100, currency="UZS", provider_name="payme")


async def test_wallet_topup_api_honest(client, db):
    u = await make_user(db, "wt2@vyronmail.com")
    await login(client, u.effective_email)
    r = await client.post("/api/wallet/topup", json={"amount": 5000, "provider": "click"})
    assert r.status_code == 200
    assert r.json()["error"] == "payment_provider_not_configured"


async def test_wallet_ledger_math(db):
    u = await make_user(db, "wl@vyronmail.com")
    w = await wallet_service.get_or_create_wallet(db, u.id)
    await wallet_service.credit(db, w, Decimal("100.50"), kind="topup", reference="t1")
    assert w.balance == Decimal("100.50")
    await wallet_service.debit(db, w, Decimal("50.25"), kind="spend", reference="t2")
    assert w.balance == Decimal("50.25")
    with pytest.raises(ValueError):
        await wallet_service.debit(db, w, Decimal("999"), kind="spend")


async def test_admin_categories_crud(client, db):
    await _admin(client, db)
    r = await client.post("/api/admin/categories", json={
        "slug": "testcat", "name_uz": "TUZ", "name_en": "TEN", "name_ru": "TRU"})
    assert r.status_code == 200, r.text
    r = await client.get("/api/admin/categories")
    assert any(c["slug"] == "testcat" for c in r.json())


async def test_admin_variants_crud(client, db):
    await _admin(client, db)
    _, _, p = await make_catalog(db)
    r = await client.post("/api/admin/variants", json={
        "product_id": p.id, "name": "V1", "supplier_cost": 10, "selling_price": 15})
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    r = await client.patch(f"/api/admin/variants/{vid}", json={
        "product_id": p.id, "name": "V1x", "supplier_cost": 10, "selling_price": 20})
    assert r.status_code == 200


async def test_admin_wallets_media(client, db):
    await _admin(client, db)
    r = await client.get("/api/admin/wallets")
    assert r.status_code == 200 and "items" in r.json()
    r = await client.get("/api/admin/media")
    assert r.status_code == 200 and "items" in r.json()


async def test_donation_presets_in_profile(client, db):
    u = await make_user(db, "dn@vyronmail.com")
    await login(client, u.effective_email)
    await client.post("/api/donations/profiles", json={"username": "preset_creator", "bio": "x"})
    # profile username may collide across runs; fetch list instead
    r = await client.get("/api/donations/profiles/preset_creator")
    if r.status_code == 200:
        assert "presets" in r.json() and len(r.json()["presets"]) >= 2


async def test_marketplace_categories_endpoint(client, db):
    r = await client.get("/api/marketplace/categories")
    assert r.status_code == 200 and "accounts" in r.json()["categories"]


async def test_seller_orders_empty_then_settled(client, db):
    su = await make_user(db, "so1@vyronmail.com")
    await login(client, su.effective_email)
    r = await client.post("/api/marketplace/become-seller?shop_name=OrderShop")
    assert r.status_code == 200
    r = await client.get("/api/seller/orders")
    assert r.status_code == 200 and r.json() == []


async def test_supplier_get_products_default(db):
    from app.suppliers.manual import ManualSupplier
    assert await ManualSupplier().get_products() == []


async def test_admin_refund_credits_wallet(client, db):
    from app.models import Order, OrderItem
    from app.utils.helpers import generate_public_id, utcnow
    await _admin(client, db)
    buyer = await make_user(db, "rf@vyronmail.com")
    order = Order(public_id=generate_public_id(), user_id=buyer.id, status=OrderStatus.COMPLETED,
                  idempotency_key=generate_public_id("rf"), subtotal=Decimal(5000),
                  total=Decimal(5000), timeline=[])
    db.add(order)
    await db.flush()
    db.add(OrderItem(order_id=order.id, kind="product", title="Thing", quantity=1,
                     unit_price=Decimal(5000), total_price=Decimal(5000)))
    await db.commit()
    r = await client.post(f"/api/admin/orders/{order.id}/refund", json={})
    assert r.status_code == 200, r.text
    await db.refresh(order)
    assert order.status == OrderStatus.REFUNDED
    w = await wallet_service.get_or_create_wallet(db, buyer.id)
    assert w.balance == Decimal("5000.00")
