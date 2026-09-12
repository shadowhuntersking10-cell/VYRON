"""Order engine: numbering, idempotency, state machine, honest payment errors."""

from __future__ import annotations

import re
import uuid


def _buy(c, token, variant_id, key=None, fields=None):
    return c.post(
        "/api/checkout/buy-now",
        json={
            "variant_id": variant_id,
            "quantity": 1,
            "required_field_values": fields or {"player_id": "8887776665"},
            "idempotency_key": key or f"k-{uuid.uuid4().hex}",
        },
        headers={"x-csrf-token": token},
    )


def test_order_number_format(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = _buy(c, token, catalog["small_variant"])
    assert res.status_code == 200, res.text
    number = res.json()["data"]["order"]["number"]
    assert re.match(r"^VYR-\d{4}-\d{6}$", number), number


def test_buy_now_is_idempotent(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    key = f"dbl-{uuid.uuid4().hex}"
    r1 = _buy(c, token, catalog["small_variant"], key=key)
    r2 = _buy(c, token, catalog["small_variant"], key=key)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["data"]["order"]["id"] == r2.json()["data"]["order"]["id"]
    orders = c.get("/api/orders").json()["data"]
    ids = [o["id"] for o in orders["items"]]
    assert ids.count(r1.json()["data"]["order"]["id"]) == 1  # only ONE order exists


def test_order_starts_created_and_is_not_fake_paid(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    res = _buy(c, token, catalog["small_variant"])
    order = res.json()["data"]["order"]
    assert order["status"] == "CREATED"
    assert order["paid_at"] is None
    assert res.json()["data"]["payment"] is None  # nothing configured → no payment invented


def test_pay_without_configured_provider_is_honest_error(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    order = _buy(c, token, catalog["small_variant"]).json()["data"]["order"]
    res = c.post(f"/api/orders/{order['id']}/pay", json={"provider": "stripe"}, headers={"x-csrf-token": token})
    assert res.status_code in (400, 422, 503)
    assert res.json()["error"]["code"] == "PAYMENT_PROVIDER_NOT_CONFIGURED"
    # order must remain unpaid
    detail = c.get(f"/api/orders/{order['id']}").json()["data"]
    assert detail["status"] == "CREATED"
    assert detail["payment"] is None


def test_available_providers_empty_without_credentials(client):
    res = client.get("/api/payment-providers")
    assert res.status_code in (200, 401)
    if res.status_code == 200:
        assert res.json()["data"] == []


def test_state_machine_blocks_invalid_transitions(db_session_factory):
    from vyron.services.order_service import can_transition

    # CREATED may go to PAYMENT_PENDING / CANCELLED / MANUAL_REVIEW / FAILED only
    assert can_transition("CREATED", "PAYMENT_PENDING")
    assert can_transition("CREATED", "CANCELLED")
    assert not can_transition("CREATED", "COMPLETED")
    assert not can_transition("CREATED", "PAID")
    assert not can_transition("PAYMENT_PENDING", "COMPLETED")  # must pass PAID/PROCESSING first
    assert not can_transition("COMPLETED", "PAID")
    assert not can_transition("CANCELLED", "PROCESSING")  # terminal


def test_webhook_without_valid_signature_rejected(client):
    for provider in ("stripe", "payme", "click"):
        res = client.post(f"/api/webhooks/payments/{provider}", json={"amount": 100, "status": "paid"})
        assert res.status_code in (400, 401, 403, 404, 422)
        assert res.json()["success"] is False
        assert res.json()["error"]["code"] != "INTERNAL_ERROR"


def test_cancel_order(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    order = _buy(c, token, catalog["small_variant"]).json()["data"]["order"]
    res = c.post(f"/api/orders/{order['id']}/cancel", json={"reason": "changed my mind"}, headers={"x-csrf-token": token})
    assert res.status_code == 200, res.text
    detail = c.get(f"/api/orders/{order['id']}").json()["data"]
    assert detail["status"] == "CANCELLED"
    assert len(detail["timeline"]) >= 2


def test_refund_request_requires_paid_order(auth_client_factory, catalog):
    c, user, token = auth_client_factory()
    order = _buy(c, token, catalog["small_variant"]).json()["data"]["order"]
    res = c.post(f"/api/orders/{order['id']}/refund-request", json={"reason": "want refund"}, headers={"x-csrf-token": token})
    assert res.status_code in (400, 422)  # unpaid order cannot be refunded
    assert res.json()["success"] is False
