"""Test setup: isolated SQLite DB, seeded catalog, TestClient."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB = "/tmp/vyron_test.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["APP_ENV"] = "testing"
os.environ["APP_SECRET"] = "test-secret"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token_123"
os.environ["ADMIN_TELEGRAM_IDS"] = "999111222"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.app import create_app  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture(scope="session")
def app():
    init_db()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def _registered(client):
    r = client.post("/api/auth/register", json={
        "username": "testuser", "email": "test@vyron.test",
        "password": "StrongPass1", "password_confirm": "StrongPass1"})
    assert r.status_code in (200, 400)
    return True


@pytest.fixture()
def user_client(client, _registered):
    """Fresh logged-in user client per test (immune to logout/reset in other tests)."""
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.post("/api/auth/login", json={"login": "testuser", "password": "StrongPass1"})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture(scope="session")
def admin_client(client):
    """Admin user created via Telegram admin flow."""
    import hashlib
    import hmac
    import json as _json
    import time
    from urllib.parse import urlencode

    bot_token = "test_bot_token_123"
    user = {"id": 999111222, "first_name": "Admin", "username": "admin_tg"}
    params = {"auth_date": str(int(time.time())),
              "query_id": "AAEx", "user": _json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    init_data = urlencode(params)
    c = TestClient(client.app, raise_server_exceptions=False)
    r = c.post("/api/auth/telegram", json={"init_data": init_data})
    assert r.status_code == 200, r.text
    assert "admin" in r.json()["user"]["roles"]
    return c
