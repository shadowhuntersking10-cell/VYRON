"""Seller marketplace lifecycle, support tickets, donation pages & fees."""

from __future__ import annotations

import uuid


def _listing_payload():
    return {
        "title": f"Test listing {uuid.uuid4().hex[:6]}",
        "description": "pytest listing",
        "price": "30.00",
        "currency": "USD",
        "delivery_type": "MANUAL",
        "sensitive_delivery_data": f"SECRET-CODE-{uuid.uuid4().hex[:6]}",
    }


def test_seller_lifecycle_and_privacy(auth_client_factory):
    c, user, token = auth_client_factory()

    # not a seller yet
    assert c.get("/api/seller/me").status_code == 403

    # apply
    res = c.post("/api/seller/apply", json={"display_name": "Pytest Seller", "description": "d"}, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text

    # create draft listing
    payload = _listing_payload()
    secret = payload["sensitive_delivery_data"]
    res = c.post("/api/seller/listings", json=payload, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text
    listing = res.json()["data"]
    assert listing["status"] == "DRAFT"

    # submit for review
    res = c.post(f"/api/seller/listings/{listing['id']}/submit", headers={"x-csrf-token": token})
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "PENDING_REVIEW"

    # admin sees it pending and approves
    ca, admin, atok = auth_client_factory(role="SUPER_ADMIN")
    pending_data = ca.get("/api/admin/listings/pending").json()["data"]
    pending = pending_data["items"] if isinstance(pending_data, dict) else pending_data
    assert any(p["id"] == listing["id"] for p in pending)
    res = ca.post(f"/api/admin/listings/{listing['id']}/review", json={"approve": True}, headers={"x-csrf-token": atok})
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "APPROVED"

    # public marketplace shows the listing but NEVER its sensitive delivery data
    public = c.get(f"/api/marketplace/listings/{listing['id']}")
    assert public.status_code == 200
    assert secret not in public.text
    market = c.get("/api/marketplace/listings")
    assert secret not in market.text

    # owner cannot buy their own listing
    res = c.post(f"/api/marketplace/listings/{listing['id']}/purchase", json={"idempotency_key": "self-buy"}, headers={"x-csrf-token": token})
    assert res.status_code in (400, 403, 422)
    assert res.json()["error"]["code"] == "SELF_PURCHASE"

    # third-party purchase fails honestly (no payment provider credentials)
    cb, buyer, btok = auth_client_factory()
    res = cb.post(
        f"/api/marketplace/listings/{listing['id']}/purchase",
        json={"provider": "stripe", "idempotency_key": "third-buy"},
        headers={"x-csrf-token": btok},
    )
    assert res.status_code in (400, 422, 503)
    assert res.json()["error"]["code"] == "PAYMENT_PROVIDER_NOT_CONFIGURED"

    # seller balance/payout endpoints reachable
    assert c.get("/api/seller/me").status_code == 200
    assert c.get("/api/seller/listings").status_code == 200
    assert c.get("/api/seller/orders").status_code == 200
    assert c.get("/api/seller/balance/transactions").status_code == 200
    assert c.get("/api/seller/payouts").status_code == 200


def test_payout_requires_minimum_and_balance(auth_client_factory):
    c, user, token = auth_client_factory()
    c.post("/api/seller/apply", json={"display_name": "Payout Seller"}, headers={"x-csrf-token": token})
    res = c.post(
        "/api/seller/payouts",
        json={"amount": "99999.00", "method": "CARD", "details": "8600***1234", "idempotency_key": "po-1"},
        headers={"x-csrf-token": token},
    )
    assert res.status_code in (400, 409, 422)
    assert res.json()["success"] is False  # no fake balance → no payout


def test_support_ticket_thread(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.post("/api/support/tickets", json={"subject": "Help", "message": "I need help", "category": "GENERAL"}, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text
    ticket_id = res.json()["data"]["id"]

    res = c.post(f"/api/support/tickets/{ticket_id}/messages", json={"body": "ping"}, headers={"x-csrf-token": token})
    assert res.status_code == 200

    ca, admin, atok = auth_client_factory(role="SUPER_ADMIN")
    res = ca.post(f"/api/admin/tickets/{ticket_id}/messages", json={"body": "pong"}, headers={"x-csrf-token": atok})
    assert res.status_code == 200

    detail = c.get(f"/api/support/tickets/{ticket_id}").json()["data"]
    assert len(detail["messages"]) == 3  # original + 2 replies
    assert detail["status"] in ("OPEN", "WAITING_USER", "IN_PROGRESS")

    res = ca.post(f"/api/admin/tickets/{ticket_id}/status", json={"status": "CLOSED"}, headers={"x-csrf-token": atok})
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "CLOSED"


def test_other_users_cannot_read_ticket(auth_client_factory):
    c, user, token = auth_client_factory()
    ticket_id = c.post("/api/support/tickets", json={"subject": "Private", "message": "secret body"}, headers={"x-csrf-token": token}).json()["data"]["id"]
    c2, user2, token2 = auth_client_factory()
    res = c2.get(f"/api/support/tickets/{ticket_id}")
    assert res.status_code in (403, 404)


def test_donation_page_and_fee_math(auth_client_factory, db_session_factory):
    c, user, token = auth_client_factory()

    res = c.put("/api/donations/me/page", json={"title": "Support my streams", "description": "d", "goal_amount": "500", "active": True}, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text

    page = c.get(f"/api/donations/page/{user['username']}")
    assert page.status_code == 200

    ssr = c.get(f"/donate/{user['username']}", headers={"Accept": "text/html"})
    assert ssr.status_code == 200

    # donation without a configured provider must fail honestly
    c2, donor, token2 = auth_client_factory()
    res = c2.post(
        "/api/donations",
        json={"username": user["username"], "amount": "25", "currency": "USD", "provider": "stripe", "idempotency_key": "don-1"},
        headers={"x-csrf-token": token2},
    )
    assert res.status_code in (400, 422, 503)
    assert res.json()["error"]["code"] == "PAYMENT_PROVIDER_NOT_CONFIGURED"

    # fee math: default 5% configured in platform settings
    from decimal import Decimal

    from vyron.db.base import get_session_factory
    from vyron.services import settings_service

    db = get_session_factory()()
    try:
        settings_service.ensure_defaults(db)
        db.commit()
        fee = settings_service.donation_fee(db, Decimal("100.00"))
        pct = settings_service.get_decimal_setting(db, "donation_fee_pct", "0")
        fixed = settings_service.get_decimal_setting(db, "donation_fee_fixed", "0")
        assert pct == Decimal("5.0")  # documented default: 5% donation platform fee
        assert fee == (Decimal("100.00") * pct / Decimal(100) + fixed).quantize(Decimal("0.01"))
        assert fee == Decimal("5.00")
    finally:
        db.close()


def test_notification_lifecycle(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.get("/api/notifications")
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    assert any(i.get("event") == "welcome" or "welcome" in str(i.get("title", "")).lower() for i in items)
    if items:
        nid = items[0]["id"]
        assert c.post(f"/api/notifications/{nid}/read", headers={"x-csrf-token": token}).status_code == 200
    assert c.post("/api/notifications/read-all", headers={"x-csrf-token": token}).status_code == 200
