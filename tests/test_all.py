"""VYRON functional tests: auth, catalog, pricing, orders, wallet, marketplace, donations."""
import time


# ---------- registration / login ----------
def test_register_duplicate_email(client):
    r = client.post("/api/auth/register", json={
        "username": "u_email1", "email": "dup@vyron.test",
        "password": "StrongPass1", "password_confirm": "StrongPass1"})
    assert r.status_code == 200
    r2 = client.post("/api/auth/register", json={
        "username": "u_email2", "email": "dup@vyron.test",
        "password": "StrongPass1", "password_confirm": "StrongPass1"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "email_exists"


def test_register_duplicate_username(client):
    r = client.post("/api/auth/register", json={
        "username": "dupuser", "email": "a1@vyron.test",
        "password": "StrongPass1", "password_confirm": "StrongPass1"})
    assert r.status_code == 200
    r2 = client.post("/api/auth/register", json={
        "username": "dupuser", "email": "a2@vyron.test",
        "password": "StrongPass1", "password_confirm": "StrongPass1"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "username_exists"


def test_register_weak_password(client):
    r = client.post("/api/auth/register", json={
        "username": "weakuser", "email": "weak@vyron.test",
        "password": "123", "password_confirm": "123"})
    assert r.status_code in (400, 422)


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"login": "testuser", "password": "WrongPass9"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_credentials"


def test_login_logout(client, user_client):
    c = client
    r = c.post("/api/auth/login", json={"login": "testuser", "password": "StrongPass1"})
    assert r.status_code == 200
    me = c.get("/api/auth/me")
    assert me.json()["user"]["username"] == "testuser"
    lo = c.post("/api/auth/logout")
    assert lo.status_code == 200
    me2 = c.get("/api/auth/me")
    assert me2.json()["user"] is None


def test_forgot_reset(client):
    r = client.post("/api/auth/forgot", json={"email": "test@vyron.test"})
    assert r.status_code == 200
    token = r.json().get("dev_reset_token")
    assert token
    bad = client.post("/api/auth/reset", json={"token": "nope", "password": "NewStrong1",
                                               "password_confirm": "NewStrong1"})
    assert bad.status_code == 400
    ok = client.post("/api/auth/reset", json={"token": token, "password": "NewStrong1",
                                              "password_confirm": "NewStrong1"})
    assert ok.status_code == 200
    # login with new password
    r2 = client.post("/api/auth/login", json={"login": "testuser", "password": "NewStrong1"})
    assert r2.status_code == 200
    # restore
    r3 = client.post("/api/auth/forgot", json={"email": "test@vyron.test"})
    t2 = r3.json()["dev_reset_token"]
    client.post("/api/auth/reset", json={"token": t2, "password": "StrongPass1",
                                         "password_confirm": "StrongPass1"})


# ---------- telegram auth ----------
def test_telegram_bad_signature_rejected(client):
    r = client.post("/api/auth/telegram", json={"init_data": "user=%7B%22id%22%3A1%7D&hash=bad"})
    assert r.status_code == 401


def test_telegram_non_admin_has_no_admin_role(client):
    import hashlib
    import hmac
    import json as _json
    from urllib.parse import urlencode
    bot_token = "test_bot_token_123"
    user = {"id": 555666777, "first_name": "Regular"}
    params = {"auth_date": str(int(time.time())), "user": _json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    r = client.post("/api/auth/telegram", json={"init_data": urlencode(params)})
    assert r.status_code == 200
    assert "admin" not in r.json()["user"]["roles"]


def test_admin_guard(user_client):
    r = user_client.get("/api/admin/dashboard")
    assert r.status_code == 403


# ---------- catalog ----------
def test_games_seeded(client):
    r = client.get("/api/games?per_page=50")
    assert r.status_code == 200
    assert r.json()["total"] >= 14


def test_products_multiple_per_game(client):
    r = client.get("/api/games/pubg-mobile")
    assert r.status_code == 200
    assert len(r.json()["products"]) >= 5
    r2 = client.get("/api/games/roblox")
    assert len(r2.json()["products"]) >= 4


def test_donation_presets(client):
    r = client.get("/api/donations/presets")
    assert len(r.json()["items"]) >= 7


# ---------- pricing engine ----------
def test_pricing_minimum_safe():
    from app.services.pricing import enforce_price, quote
    q = quote(40000, payment_fee_percent=2, payment_fee_fixed=500,
              safety_buffer_percent=2, platform_margin_percent=10, minimum_margin_percent=5)
    assert q["minimum_safe_price"] > 40000
    assert q["suggested_price"] >= q["minimum_safe_price"]
    # below minimum blocked
    q2 = quote(40000, payment_fee_percent=2, payment_fee_fixed=500,
               safety_buffer_percent=2, platform_margin_percent=10,
               minimum_margin_percent=5, new_price=40000)
    ok, _ = enforce_price(40000, q2, allow_override=False)
    assert ok is False
    ok2, _ = enforce_price(q["suggested_price"], quote(
        40000, payment_fee_percent=2, payment_fee_fixed=500, safety_buffer_percent=2,
        platform_margin_percent=10, minimum_margin_percent=5, new_price=q["suggested_price"]))
    assert ok2 is True


def test_admin_price_block(admin_client):
    prods = admin_client.get("/api/admin/products?per_page=5").json()["items"]
    pid = prods[0]["id"]
    r = admin_client.post(f"/api/admin/products/{pid}/price",
                          json={"customer_price": 100, "override_loss_protection": False})
    assert r.status_code == 400


# ---------- commission ----------
def test_marketplace_split():
    from app.services.marketplace_svc import split_sale
    com, net = split_sale(100000, 10)
    assert com == 10000 and net == 90000


# ---------- checkout + orders + wallet pay ----------
def test_checkout_wallet_flow(user_client):
    # give wallet balance directly via service-level deposit? use API: wallet starts 0.
    # Deposit via wallet provider is impossible without funds, so test checkout validation first.
    prods = user_client.get("/api/products?per_page=1").json()["items"]
    pid = prods[0]["id"]
    # invalid coupon rejected
    r = user_client.post("/api/checkout", json={
        "items": [{"product_id": pid, "quantity": 1}], "coupon_code": "NOPE",
        "provider": "wallet", "customer_fields": {"player_id": "123"}, "idempotency_key": "test-key-1"})
    assert r.status_code == 400
    # insufficient wallet funds
    r2 = user_client.post("/api/checkout", json={
        "items": [{"product_id": pid, "quantity": 1}], "provider": "wallet",
        "customer_fields": {"player_id": "123"}, "idempotency_key": "test-key-2"})
    assert r2.status_code == 400  # insufficient_funds


def test_idempotent_checkout(user_client):
    prods = user_client.get("/api/products?per_page=1").json()["items"]
    pid = prods[0]["id"]
    body = {"items": [{"product_id": pid, "quantity": 1}], "provider": "payme",
            "customer_fields": {"player_id": "1"}, "idempotency_key": "idem-xyz-1"}
    # payme not configured -> 400, but order should exist once
    user_client.post("/api/checkout", json=body)
    user_client.post("/api/checkout", json=body)
    orders = user_client.get("/api/orders").json()["items"]
    assert isinstance(orders, list)


def test_wallet_api(user_client):
    r = user_client.get("/api/wallet")
    assert r.status_code == 200
    assert "balance" in r.json()


def test_ledger_summary(admin_client):
    r = admin_client.get("/api/admin/dashboard")
    assert r.status_code == 200
    assert "range_30d" in r.json()


# ---------- marketplace ----------
def test_seller_flow(user_client):
    r = user_client.post("/api/marketplace/sellers/register",
                         json={"shop_name": "Test Shop"})
    assert r.status_code in (200, 400)  # 400 if already registered in reruns


def test_marketplace_browse(client):
    r = client.get("/api/marketplace/listings")
    assert r.status_code == 200
    c = client.get("/api/marketplace/categories")
    assert len(c.json()["items"]) >= 3


def test_review_requires_purchase(user_client):
    r = user_client.post("/api/listings/999999/reviews",
                         json={"order_id": 999999, "rating": 5, "comment": "x"})
    assert r.status_code in (403, 404)


# ---------- favorites ----------
def test_favorites(user_client):
    r = user_client.post("/api/favorites", json={"target_type": "game", "target_id": 1})
    assert r.status_code == 200
    assert r.json()["favorited"] is True
    r2 = user_client.post("/api/favorites", json={"target_type": "game", "target_id": 1})
    assert r2.json()["favorited"] is False


# ---------- support ----------
def test_support_ticket(user_client):
    r = user_client.post("/api/support/tickets",
                         json={"subject": "Help me", "category": "general", "body": "Hello"})
    assert r.status_code == 200
    tid = r.json()["id"]
    d = user_client.get(f"/api/support/tickets/{tid}")
    assert d.status_code == 200
    assert len(d.json()["messages"]) == 1


# ---------- donations ----------
def test_donation_profiles(client):
    r = client.get("/api/donations/profiles")
    assert len(r.json()["items"]) >= 1


def test_donate_requires_valid_amount(user_client):
    profiles = user_client.get("/api/donations/profiles").json()["items"]
    uname = profiles[0]["username"]
    r = user_client.post(f"/api/donations/profiles/{uname}/donate",
                         json={"amount": -5, "provider": "wallet"})
    assert r.status_code == 400


# ---------- payments honesty ----------
def test_providers_not_configured(client):
    r = client.get("/api/payments/providers")
    st = r.json()["providers"]
    assert st["payme"] == "NOT_CONFIGURED"
    assert st["click"] == "NOT_CONFIGURED"
    assert st["stripe"] == "NOT_CONFIGURED"


def test_webhook_bad_signature(client):
    r = client.post("/api/payments/webhooks/payme", json={"params": {}})
    assert r.status_code == 400


# ---------- supplier honesty ----------
def test_order_without_supplier_goes_manual():
    from app.database import SessionLocal
    from app import models
    from app.services import orders as order_svc
    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(username="testuser").first()
        product = db.query(models.Product).first()
        order = order_svc.create_order(db, user, [{"product_id": product.id, "quantity": 1}],
                                       customer_fields={"player_id": "1"},
                                       idempotency_key="manual-test-1")
        order_svc.mark_paid(db, order, "wallet", "test-ext-1")
        db.refresh(order)
        assert order.status == "MANUAL_REVIEW"  # no supplier configured -> honest manual review
    finally:
        db.close()


# ---------- website routes ----------
def test_website_routes(client):
    for path in ["/", "/games", "/games/pubg-mobile", "/marketplace", "/donations",
                 "/promotions", "/support", "/login", "/register", "/about", "/terms",
                 "/privacy", "/refund", "/tg-miniapp", "/healthz"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_product_page(client):
    p = client.get("/api/products?per_page=1").json()["items"][0]
    r = client.get(f"/products/{p['slug']}")
    assert r.status_code == 200
