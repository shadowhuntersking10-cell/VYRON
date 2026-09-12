"""Authentication: registration validation, login, sessions, logout, password change."""

from __future__ import annotations

import uuid


def _register(client, token, **overrides):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Auth {suffix}",
        "username": f"a_{suffix}",
        "email": f"a_{suffix}@example.com",
        "password": "Str0ng!Pass2026",
        "confirm_password": "Str0ng!Pass2026",
        "locale": "en",
    }
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload, headers={"x-csrf-token": token})


def test_register_success(client, csrf):
    res = _register(client, csrf)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["role"] == "USER"
    assert "password" not in data and "password_hash" not in data


def test_register_rejects_weak_password(client, csrf):
    res = _register(client, csrf, password="abc", confirm_password="abc")
    assert res.status_code == 422
    assert res.json()["success"] is False


def test_register_rejects_mismatched_confirmation(client, csrf):
    res = _register(client, csrf, confirm_password="Different!Pass2026")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "PASSWORDS_MISMATCH"


def test_register_rejects_duplicate_username(client, csrf):
    suffix = uuid.uuid4().hex[:8]
    first = _register(client, csrf, username=f"dup_{suffix}", email=f"dup1_{suffix}@example.com")
    assert first.status_code == 200
    second = _register(client, csrf, username=f"dup_{suffix}", email=f"dup2_{suffix}@example.com")
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "USERNAME_TAKEN"


def test_login_wrong_password_is_rejected(client, csrf):
    suffix = uuid.uuid4().hex[:8]
    email = f"login_{suffix}@example.com"
    _register(client, csrf, email=email)
    res = client.post("/api/auth/login", json={"email": email, "password": "Wrong!Pass999"}, headers={"x-csrf-token": csrf})
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_session_cookie_is_httponly_and_me_works(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["data"]["id"] == user["id"]
    # TestClient stores cookies; re-login to capture Set-Cookie attributes
    res2 = c.post("/api/auth/login", json={"email": user["email"], "password": "Str0ng!Pass2026"}, headers={"x-csrf-token": token})
    set_cookie = res2.headers.get("set-cookie", "")
    assert "vyron_session" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite" in set_cookie


def test_logout_invalidates_session(auth_client_factory):
    c, user, token = auth_client_factory()
    assert c.get("/api/auth/me").json().get("data") is not None
    res = c.post("/api/auth/logout", headers={"x-csrf-token": token})
    assert res.status_code == 200
    # /me is anonymous-tolerant by design (200 + null data); protected routes must 401
    assert c.get("/api/auth/me").json().get("data") is None
    assert c.get("/api/orders").status_code == 401


def test_logout_all_revokes_every_session(auth_client_factory):
    c1, user, token1 = auth_client_factory()
    # second session for the same user
    c2 = c1.__class__(c1.app, raise_server_exceptions=False)
    c2.get("/api/i18n/en")
    token2 = c2.cookies.get("vyron_csrf") or ""
    res = c2.post("/api/auth/login", json={"email": user["email"], "password": "Str0ng!Pass2026"}, headers={"x-csrf-token": token2})
    assert res.status_code == 200
    assert c2.get("/api/auth/me").json().get("data") is not None

    res = c1.post("/api/auth/logout-all", headers={"x-csrf-token": token1})
    assert res.status_code == 200
    assert c2.get("/api/auth/me").json().get("data") is None
    assert c1.get("/api/orders").status_code == 401


def test_change_password(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/auth/change-password",
        json={"current_password": "Str0ng!Pass2026", "new_password": "Ev3nStr0nger!2026", "confirm_password": "Ev3nStr0nger!2026"},
        headers={"x-csrf-token": token},
    )
    assert res.status_code == 200, res.text
    res = c.post("/api/auth/login", json={"email": user["email"], "password": "Ev3nStr0nger!2026"}, headers={"x-csrf-token": token})
    assert res.status_code == 200


def test_change_password_wrong_current_rejected(auth_client_factory):
    c, user, token = auth_client_factory()
    res = c.post(
        "/api/auth/change-password",
        json={"current_password": "NotMyPassword!1", "new_password": "Ev3nStr0nger!2026", "confirm_password": "Ev3nStr0nger!2026"},
        headers={"x-csrf-token": token},
    )
    assert res.status_code in (401, 403, 422)
    assert res.json()["success"] is False


def test_argon2id_is_used_for_passwords(db_session_factory):
    from sqlalchemy import select

    from vyron.db.base import get_session_factory
    from vyron.db.models import User
    from vyron.security.hashing import hash_password

    fresh = hash_password("Whatever!Pass123")
    assert fresh.startswith("$argon2id$"), f"unexpected hash scheme: {fresh[:20]}"
    db = get_session_factory()()
    try:
        user = db.scalar(select(User).limit(1))
        assert user is None or user.password_hash.startswith("$argon2id$")
    finally:
        db.close()
