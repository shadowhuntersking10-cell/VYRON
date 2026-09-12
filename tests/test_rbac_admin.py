"""Server-side authorization: SSR gates, admin API gates, admin operations, audit trail."""

from __future__ import annotations


def test_admin_api_forbidden_for_regular_user(auth_client_factory):
    c, user, token = auth_client_factory()
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/settings", "/api/admin/revenue/summary"):
        res = c.get(path)
        assert res.status_code == 403, f"{path} returned {res.status_code}"
        assert res.json()["error"]["code"] == "FORBIDDEN"


def test_admin_api_mutation_forbidden_for_regular_user(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.put("/api/admin/settings", json={"marketplace_commission_pct": "1"}, headers={"x-csrf-token": token})
    assert res.status_code == 403


def test_admin_ssr_gate(auth_client_factory):
    # regular user: 404 (existence not disclosed)
    c, user, token = auth_client_factory()
    res = c.get("/admin", headers={"Accept": "text/html"})
    assert res.status_code == 404

    # anonymous: redirect to login
    from fastapi.testclient import TestClient

    anon = TestClient(c.app, raise_server_exceptions=False)
    res = anon.get("/admin", headers={"Accept": "text/html"}, follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]

    # super admin: full shell
    ca, admin, tok = auth_client_factory(role="SUPER_ADMIN")
    res = ca.get("/admin", headers={"Accept": "text/html"})
    assert res.status_code == 200
    assert "admin" in res.text.lower()


def test_seller_area_gate(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.get("/api/seller/me")
    assert res.status_code == 403
    res = c.get("/seller", headers={"Accept": "text/html"}, follow_redirects=False)
    assert res.status_code in (200, 302)  # apply page or redirect, never the seller panel


def test_admin_dashboard_endpoints(auth_client_factory):
    c, admin, token = auth_client_factory(role="SUPER_ADMIN")
    for path in (
        "/api/admin/stats",
        "/api/admin/charts?days=7",
        "/api/admin/queue-health",
        "/api/admin/catalog-counts",
        "/api/admin/users",
        "/api/admin/orders",
        "/api/admin/payments",
        "/api/admin/refunds",
        "/api/admin/suppliers",
        "/api/admin/sellers",
        "/api/admin/listings/pending",
        "/api/admin/payouts",
        "/api/admin/donations",
        "/api/admin/coupons",
        "/api/admin/promotions",
        "/api/admin/audit-logs",
        "/api/admin/fraud",
        "/api/admin/tickets",
        "/api/admin/webhook-events",
        "/api/admin/telegram/stats",
        "/api/admin/settings",
        "/api/admin/revenue/summary?range=30",
        "/api/admin/revenue/series?range=30",
        "/api/admin/revenue/by-game?range=30",
        "/api/admin/revenue/by-product?range=30",
    ):
        res = c.get(path)
        assert res.status_code == 200, f"{path} -> {res.status_code}: {res.text[:200]}"
        assert res.json()["success"] is True


def test_admin_settings_roundtrip_and_audit(auth_client_factory):
    c, admin, token = auth_client_factory(role="SUPER_ADMIN")
    before = c.get("/api/admin/settings").json()["data"]["settings"]["marketplace_commission_pct"]
    res = c.put("/api/admin/settings", json={"marketplace_commission_pct": "13"}, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["settings"]["marketplace_commission_pct"] == "13"

    audit = c.get("/api/admin/audit-logs?action=settings.").json()["data"]["items"]
    assert any(a["action"] == "settings.updated" and a["source"] == "admin_action" for a in audit)

    # restore
    res = c.put("/api/admin/settings", json={"marketplace_commission_pct": before}, headers={"x-csrf-token": token})
    assert res.status_code == 200


def test_admin_settings_rejects_out_of_range(auth_client_factory):
    c, admin, token = auth_client_factory(role="SUPER_ADMIN")
    res = c.put("/api/admin/settings", json={"marketplace_commission_pct": "150"}, headers={"x-csrf-token": token})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "SETTING_INVALID"


def test_revenue_never_counts_unverified_events(auth_client_factory, catalog):
    """Orders that were never paid must contribute ZERO to revenue reporting."""
    cu, buyer, utok = auth_client_factory()
    res = cu.post(
        "/api/checkout/buy-now",
        json={"variant_id": catalog["small_variant"], "quantity": 2, "required_field_values": {"player_id": "3131313131"}, "idempotency_key": "rev-test-1"},
        headers={"x-csrf-token": utok},
    )
    assert res.status_code == 200

    ca, admin, atok = auth_client_factory(role="SUPER_ADMIN")
    summary = ca.get("/api/admin/revenue/summary?range=90").json()["data"]["summary"]
    from decimal import Decimal

    assert Decimal(summary["gross_revenue"]) == Decimal("0.00")
    assert Decimal(summary["net_revenue"]) == Decimal("0.00")
