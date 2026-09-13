"""Round 3: pricing engine, FX, media assign, presets/categories DB,
Stars provider, auth hardening, revenue tops, aliases."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models import (
    DonationPreset, MarketplaceCategory, MediaFile, UserRole,
)
from app.services import pricing_service
from tests.conftest import login, make_catalog, make_user


def _tag() -> str:
    return uuid.uuid4().hex[:8]


# ---------- pricing ----------

async def test_pricing_quote_math(db):
    _, _, p = await make_catalog(db)
    p.supplier_cost = 100
    p.payment_fee_percent = 2.0
    p.platform_margin_percent = 10.0
    q = pricing_service.quote_costs(p)
    # payment % is estimated on the candidate price: 2% of 100 = 2 -> base 102
    assert q["payment_cost"] == 2
    assert q["cost_base"] == 102
    assert q["minimum_safe_price"] == Decimal("107.10")  # 102 * 1.05
    assert q["suggested_price"] == Decimal("112.20")  # 102 * 1.10
    assert q["below_safe"] is True
    p.payment_fee_percent = None
    p.platform_margin_percent = None
    q2 = pricing_service.quote_costs(p)
    assert q2["below_safe"] is True  # 100 < 107.10 default floor: fixture sells at a loss
    assert q2["minimum_safe_price"] == Decimal("107.10")
    assert q2["suggested_price"] == Decimal("114.24")  # 102 * 1.12
    assert q2["suggested_price"] > q2["minimum_safe_price"]


async def test_pricing_blocks_loss_unless_confirmed(db):
    from app.services.pricing_service import UnsafePriceError, validate_price
    _, _, p = await make_catalog(db)
    p.supplier_cost = 100
    try:
        validate_price(p, 90)
        raise AssertionError("should have blocked")
    except UnsafePriceError as exc:
        assert "loss" in str(exc)
    p.loss_leader_allowed = True
    assert validate_price(p, 90, confirmed=True)["below_safe"] is True


async def test_admin_price_patch_blocked_then_allowed(client, db):
    admin = await make_user(db, f"pricer{_tag()}@vyronmail.com", role=UserRole.ADMIN)
    await login(client, admin.effective_email)
    _, g, p = await make_catalog(db)
    body = {"game_id": g.id, "name": p.name, "supplier_cost": 100, "selling_price": 90, "currency": "UZS"}
    r = await client.patch(f"/api/admin/products/{p.id}", json=body)
    assert r.status_code == 400, r.text
    assert "loss" in r.text
    body.update({"confirm_unsafe": True, "loss_leader_allowed": True})
    r = await client.patch(f"/api/admin/products/{p.id}", json=body)
    assert r.status_code == 200, r.text
    r = await client.get("/api/admin/pricing/overview")
    assert r.status_code == 200
    row = next(x for x in r.json() if x["id"] == p.id)
    assert row["below_safe"] is True


# ---------- FX ----------

async def test_fx_convert_and_snapshot(client, db):
    from app.services import fx_service
    assert await fx_service.convert(db, 12900, "UZS", "USD") == 1
    assert await fx_service.convert(db, 2, "USD", "UZS") == 25800
    snap = await fx_service.snapshot_for_order(db, "USD")
    assert snap["fx_base_currency"] == "UZS"
    assert snap["fx_rate"] == 12900

    # order carries an FX snapshot
    u = await make_user(db, f"fx{_tag()}@vyronmail.com")
    await login(client, u.effective_email)
    _, g, p = await make_catalog(db)
    r = await client.post("/api/checkout/orders", json={
        "product_id": p.id, "quantity": 1, "provider": "payme",
    })
    assert r.status_code == 200, r.text
    assert r.json()["order"]["fx_base_currency"] == "UZS"
    assert float(r.json()["order"]["fx_rate"]) == 1.0


# ---------- media assign ----------

async def test_media_assign_unassign(client, db):
    admin = await make_user(db, f"media{_tag()}@vyronmail.com", role=UserRole.ADMIN)
    await login(client, admin.effective_email)
    m = MediaFile(owner_id=admin.id, kind="game_logo", media_type="GAME_LOGO",
                  filename="logo.svg", path="/tmp/x.svg", url="/uploads/x.svg",
                  mime="image/svg+xml", size_bytes=10)
    db.add(m)
    await db.commit()
    _, g, _ = await make_catalog(db)
    r = await client.post(f"/api/admin/media/{m.id}/assign",
                          json={"target": "game_logo", "game_id": g.id})
    assert r.status_code == 200, r.text
    await db.refresh(g)
    assert g.logo_url == "/uploads/x.svg"
    r = await client.post(f"/api/admin/media/{m.id}/unassign", json={})
    assert r.status_code == 200, r.text
    r = await client.patch(f"/api/admin/media/{m.id}", json={"alt_text": "Test Game logo"})
    assert r.status_code == 200, r.text


# ---------- presets / categories from DB ----------

async def test_categories_db_backed(client, db):
    from decimal import Decimal
    tag = _tag()
    db.add(MarketplaceCategory(slug=f"mkt-{tag}", name_uz="T", name_en="T", name_ru="T",
                               commission_percent=Decimal("12.5")))
    await db.commit()
    r = await client.get("/api/marketplace/categories")
    assert r.status_code == 200
    data = r.json()
    assert f"mkt-{tag}" in data["categories"]
    assert any(d["slug"] == f"mkt-{tag}" and float(d["commission_percent"]) == 12.5 for d in data["detailed"])


async def test_presets_db_backed(client, db):
    from decimal import Decimal
    tag = _tag()
    currency = f"U{tag[:4]}"  # unique currency to avoid clashing with parallel rows
    db.add(DonationPreset(currency=currency, amount=Decimal("777"), sort_order=0))
    await db.commit()
    from app.services import settings_service
    assert await settings_service.donation_presets_for(db, currency) == [777.0]


# ---------- Stars provider ----------

async def test_stars_math_and_link(monkeypatch):
    from app.config import settings
    from app.payments.stars_provider import StarsProvider, stars_for_amount
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "VyronBot")
    assert stars_for_amount(12900, "UZS") == 50
    assert stars_for_amount(1, "USD") == 50
    assert stars_for_amount(100, "UZS") == 1  # minimum 1 star
    res = await StarsProvider().create_payment(amount=12900, currency="UZS", order_public_id="VYR-1")
    assert res.ok and res.checkout_url == "https://t.me/VyronBot?start=pay_VYR-1"
    assert res.raw["stars"] == 50


async def test_stars_unconfigured_without_token(monkeypatch):
    from app.config import settings
    from app.payments.stars_provider import StarsProvider
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    assert StarsProvider().configured is False


# ---------- auth hardening ----------

async def test_weak_password_rejected(client):
    r = await client.post("/api/auth/register", json={
        "email": f"weak{_tag()}@vyronmail.com", "password": "password"})
    assert r.status_code == 400, r.text
    assert "weak_password" in r.text


async def test_password_confirm_mismatch(client):
    r = await client.post("/api/auth/register", json={
        "email": f"mm{_tag()}@vyronmail.com", "password": "Str0ng!Pass1",
        "password_confirm": "SomethingElse1!"})
    assert r.status_code == 422, r.text


async def test_login_lockout_after_fails(client, db):
    from app.services import auth_service
    auth_service.reset_login_buckets()
    tag = _tag()
    u = await make_user(db, f"lock{tag}@vyronmail.com")
    for _ in range(8):
        r = await client.post("/api/auth/login", json={"login": u.effective_email, "password": "WrongPass1!"})
        assert r.status_code == 401
    r = await client.post("/api/auth/login", json={"login": u.effective_email, "password": "WrongPass1!"})
    assert r.status_code == 429
    assert "too_many_attempts" in r.text
    auth_service.reset_login_buckets()


async def test_forgot_reset_flow(client, db):
    from app.services import auth_service
    u = await make_user(db, f"forgot{_tag()}@vyronmail.com")
    r = await client.post("/api/auth/forgot", json={"login": u.effective_email})
    assert r.status_code == 200 and r.json()["ok"] is True
    # unknown login must look identical (no account probing)
    r = await client.post("/api/auth/forgot", json={"login": f"nobody{_tag()}@vyronmail.com"})
    assert r.status_code == 200 and r.json()["ok"] is True
    token = await auth_service.create_password_reset(db, u)
    await db.commit()
    r = await client.post("/api/auth/reset", json={
        "token": token, "password": "N3w!StrongPass", "password_confirm": "N3w!StrongPass"})
    assert r.status_code == 200, r.text
    r = await client.post("/api/auth/login", json={"login": u.effective_email, "password": "N3w!StrongPass"})
    assert r.status_code == 200, r.text


async def test_verify_flow(client, db):
    from app.services import auth_service
    u = await make_user(db, f"verify{_tag()}@vyronmail.com")
    await login(client, u.effective_email)
    r = await client.post("/api/auth/verify/request")
    assert r.status_code == 200, r.text
    token = await auth_service.create_email_verification(db, u)
    await db.commit()
    r = await client.post("/api/auth/verify/confirm", json={"token": token})
    assert r.status_code == 200 and r.json()["email_verified"] is True


async def test_origin_check_blocks_csrf(client):
    r = await client.post("/api/auth/login",
                          json={"login": "x@vyronmail.com", "password": "x"},
                          headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 403
    assert "bad_origin" in r.text


# ---------- listings gallery (async-safe serialization) ----------

async def test_listings_gallery_serializes(client, db):
    from app.models import MarketplaceListing, Seller
    u = await make_user(db, f"gal{_tag()}@vyronmail.com")
    s = Seller(user_id=u.id, shop_name=f"shop{_tag()}")
    db.add(s)
    await db.flush()
    row = MarketplaceListing(seller_id=s.id, title=f"Item {_tag()}", price=1000,
                             currency="UZS", category="items", status="active")
    db.add(row)
    await db.flush()
    from app.models import ListingImage
    db.add(ListingImage(listing_id=row.id, url="/static/x.svg", alt_text="pic"))
    await db.commit()
    r = await client.get("/api/marketplace/listings")
    assert r.status_code == 200, r.text
    found = [x for x in r.json() if x["id"] == row.id]
    assert found and found[0]["gallery"][0]["url"] == "/static/x.svg"
    r = await client.get(f"/api/marketplace/listings/{row.id}")
    assert r.status_code == 200 and r.json()["gallery"][0]["alt_text"] == "pic"


# ---------- order/payment notifications ----------

async def test_order_and_payment_notifications(client, db):
    from sqlalchemy import select
    from app.models import Notification, Order
    from app.payments.manager import get_payment_manager
    u = await make_user(db, f"notif{_tag()}@vyronmail.com")
    await login(client, u.effective_email)
    _, _, p = await make_catalog(db)
    r = await client.post("/api/checkout/orders", json={"product_id": p.id, "quantity": 1, "provider": "payme"})
    assert r.status_code == 200, r.text
    public_id = r.json()["order"]["public_id"]
    notes = (await db.execute(select(Notification).where(Notification.user_id == u.id))).scalars().all()
    assert any(n.title == "Order created 🧾" and public_id in (n.body or "") for n in notes)
    # service-level settlement (same path webhooks/bot use) emits payment-confirmed
    from app.models import Payment, PaymentStatus
    order = (await db.execute(select(Order).where(Order.public_id == public_id))).scalars().first()
    payment = Payment(order_id=order.id, user_id=u.id, provider="payme",
                      status=PaymentStatus.PENDING, amount=order.total,
                      currency=order.currency, idempotency_key=f"nt-{public_id}")
    db.add(payment)
    await db.commit()
    await get_payment_manager().mark_paid(db, payment, provider_payment_id="test-receipt-1",
                                          payload={"test": True})
    await db.commit()
    notes = (await db.execute(select(Notification).where(Notification.user_id == u.id))).scalars().all()
    assert any(n.title == "Payment confirmed ✅" for n in notes)


# ---------- revenue tops + aliases ----------

async def test_revenue_tops_shape(client, db):
    admin = await make_user(db, f"rev{_tag()}@vyronmail.com", role=UserRole.ADMIN)
    await login(client, admin.effective_email)
    for rng in ("today", "7d", "30d", "all"):
        r = await client.get(f"/api/admin/revenue?range={rng}")
        assert r.status_code == 200, r.text
    r = await client.get("/api/admin/revenue/tops?range=30d")
    assert r.status_code == 200
    assert set(r.json()) == {"top_games", "top_products", "top_sellers"}


async def test_page_aliases(client):
    for path in ("/login", "/register"):
        r = await client.get(path)
        assert r.status_code == 200, path
    for path in ("/profile", "/orders"):
        r = await client.get(path, follow_redirects=False)
        assert r.status_code in (302, 307), path
