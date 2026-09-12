"""Catalog exposure rules, required-field validation, server-priced cart, coupons."""

from __future__ import annotations

import uuid


def test_product_api_never_exposes_supplier_cost(client, catalog):
    res = client.get(f"/api/products/{catalog['product_slug']}")
    assert res.status_code == 200
    raw = res.text
    assert "cost_price" not in raw
    assert "0.80" not in raw  # the seeded cost value must not leak anywhere
    data = res.json()["data"]
    for variant in data["variants"]:
        assert "cost_price" not in variant


def test_games_and_products_listing(client, catalog):
    assert client.get("/api/games").status_code == 200
    assert client.get(f"/api/games/{catalog['game_slug']}").status_code == 200
    res = client.get("/api/products")
    assert res.status_code == 200
    assert "cost" not in res.text


def test_required_field_pattern_enforced(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/cart/items",
        json={"variant_id": catalog["small_variant"], "quantity": 1, "required_field_values": {"player_id": "abc"}},
        headers={"x-csrf-token": token},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FIELD_INVALID"


def test_required_field_missing_rejected(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/cart/items",
        json={"variant_id": catalog["small_variant"], "quantity": 1, "required_field_values": {}},
        headers={"x-csrf-token": token},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "REQUIRED_FIELD_MISSING"


def test_cart_is_server_priced(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/cart/items",
        json={"variant_id": catalog["small_variant"], "quantity": 3, "required_field_values": {"player_id": "1234567890"}},
        headers={"x-csrf-token": token},
    )
    assert res.status_code == 200, res.text
    cart = c.get("/api/cart").json()["data"]
    totals = cart["totals"]
    assert totals["subtotal"] == "3.00"  # 3 x $1.00, derived server-side
    assert totals["total"] == "3.00"
    # a client-supplied price is ignored entirely (no price field accepted)
    assert all("price" not in str(item.get("client_price", "")) for item in cart["items"])


def test_cart_update_and_remove(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/cart/items",
        json={"variant_id": catalog["small_variant"], "quantity": 1, "required_field_values": {"player_id": "5551234567"}},
        headers={"x-csrf-token": token},
    )
    item_id = res.json()["data"]["items"][0]["item_id"]
    res = c.patch(f"/api/cart/items/{item_id}", json={"quantity": 4}, headers={"x-csrf-token": token})
    assert res.status_code == 200
    totals = c.get("/api/cart").json()["data"]["totals"]
    assert totals["subtotal"] == "4.00"
    res = c.delete(f"/api/cart/items/{item_id}", headers={"x-csrf-token": token})
    assert res.status_code == 200
    assert c.get("/api/cart").json()["data"]["totals"]["subtotal"] == "0.00"


def test_stock_limit_enforced(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/cart/items",
        json={"variant_id": catalog["big_variant"], "quantity": 99, "required_field_values": {"player_id": "7771234567"}},
        headers={"x-csrf-token": token},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "OUT_OF_STOCK"


def test_coupon_min_order_and_unknown_code(auth_client_factory, catalog, db_session_factory):
    from decimal import Decimal

    from vyron.db.base import get_session_factory
    from vyron.db.models import Coupon

    code = f"TEST{uuid.uuid4().hex[:6].upper()}"
    db = get_session_factory()()
    try:
        db.add(Coupon(code=code, type="PERCENTAGE", value=Decimal("10"), currency="USD", max_uses=10, per_user_limit=1, min_order_amount=Decimal("100.00"), active=True))
        db.commit()
    finally:
        db.close()

    c, user, token = auth_client_factory()
    c.post(
        "/api/cart/items",
        json={"variant_id": catalog["small_variant"], "quantity": 1, "required_field_values": {"player_id": "4242424242"}},
        headers={"x-csrf-token": token},
    )
    res = c.post("/api/cart/coupon", json={"code": code}, headers={"x-csrf-token": token})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "COUPON_MIN_ORDER"

    res = c.post("/api/cart/coupon", json={"code": "NOSUCHCOUPON"}, headers={"x-csrf-token": token})
    assert res.status_code in (404, 422)
    assert res.json()["error"]["code"] == "COUPON_INVALID"
