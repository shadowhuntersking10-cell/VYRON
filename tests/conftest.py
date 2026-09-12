"""Pytest configuration — runs against the dedicated MySQL `vyron_test` database.

Environment is pinned BEFORE any vyron import so settings/database point at the
test database. Real MySQL + real Redis are required (same infra as `python main.py`);
nothing is mocked at the infrastructure layer — only external credentials are absent,
which the app must report honestly (and tests assert exactly that).
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("VYRON_ENV", "test")
os.environ["DATABASE_URL"] = "mysql+pymysql://vyron:vyron_dev_password@127.0.0.1:3306/vyron_test?charset=utf8mb4"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/1"  # db 1: isolate queues/rate-limits from the dev app on db 0
os.environ.setdefault("SESSION_SECRET", "test-session-secret-0123456789abcdef0123456789abcdef")
os.environ.setdefault("ADMIN_EMAIL", "root-admin@vyron.test")
os.environ.setdefault("ADMIN_PASSWORD", "TestAdmin!2026")
os.environ.setdefault("ADMIN_USERNAME", "root_admin")
os.environ["SEED_DEMO_DATA"] = "0"
os.environ["AUTO_MIGRATE_ON_START"] = "0"
# generous limits so tests don't trip per-IP rate limiting
os.environ["RATE_LIMIT_LOGIN"] = "10000/minute"
os.environ["RATE_LIMIT_REGISTER"] = "10000/minute"
os.environ["RATE_LIMIT_RESET"] = "10000/minute"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    from vyron.app import create_app
    from vyron.db.base import Base, get_engine

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    application = create_app()
    yield application
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _csrf(client: TestClient) -> str:
    client.get("/api/i18n/en")
    return client.cookies.get("vyron_csrf") or ""


@pytest.fixture()
def csrf(client: TestClient):
    return _csrf(client)


@pytest.fixture()
def auth_client_factory(app):
    """Register + login a fresh unique user on an ISOLATED TestClient
    (separate cookie jar), so tests can act as several users at once.
    Returns (client, user_data, csrf_token)."""

    def _make(role: str | None = None, name: str | None = None) -> tuple:
        c = TestClient(app, raise_server_exceptions=False)
        suffix = uuid.uuid4().hex[:8]
        creds = {
            "name": name or f"User {suffix}",
            "username": f"u_{suffix}",
            "email": f"u_{suffix}@example.com",
            "password": "Str0ng!Pass2026",
            "confirm_password": "Str0ng!Pass2026",
            "locale": "en",
        }
        token = _csrf(c)
        res = c.post("/api/auth/register", json=creds, headers={"x-csrf-token": token})
        assert res.status_code == 200, res.text
        res = c.post(
            "/api/auth/login",
            json={"email": creds["email"], "password": creds["password"]},
            headers={"x-csrf-token": token},
        )
        assert res.status_code == 200, res.text
        user = res.json()["data"]
        if role is not None:
            from vyron.db.base import get_session_factory
            from vyron.db.models import User

            db = get_session_factory()()
            try:
                db.get(User, user["id"]).role = role
                db.commit()
            finally:
                db.close()
        return c, user, token

    return _make


@pytest.fixture(scope="session")
def db_session_factory():
    from vyron.db.base import get_session_factory

    return get_session_factory


@pytest.fixture(scope="session")
def catalog(db_session_factory) -> dict:
    """Seed a minimal real catalog (game + product + variants) once per session."""
    from decimal import Decimal

    from vyron.db.base import get_session_factory
    from vyron.db.models import Game, Product, ProductVariant

    db = get_session_factory()()
    try:
        game = Game(
            name="Test Game",
            slug=f"test-game-{uuid.uuid4().hex[:6]}",
            description="pytest catalog",
            status="ACTIVE",
            is_featured=True,
            sort_order=0,
            required_fields=[
                {"name": "player_id", "key": "player_id", "label": "Player ID", "type": "text", "required": True, "pattern": "^\\d{6,15}$"}
            ],
        )
        db.add(game)
        db.flush()
        product = Product(
            game_id=game.id,
            name="Test Coins",
            slug=f"test-coins-{uuid.uuid4().hex[:6]}",
            type="TOPUP",
            active=True,
            is_featured=True,
            sort_order=0,
            required_fields=None,
        )
        db.add(product)
        db.flush()
        small = ProductVariant(product_id=product.id, name="100 coins", cost_price=Decimal("0.80"), selling_price=Decimal("1.00"), currency="USD", active=True, stock=-1, sort_order=0)
        big = ProductVariant(product_id=product.id, name="1000 coins", cost_price=Decimal("6.50"), selling_price=Decimal("8.00"), currency="USD", active=True, stock=5, sort_order=1)
        db.add_all([small, big])
        db.commit()
        return {"game_slug": game.slug, "product_slug": product.slug, "small_variant": small.id, "big_variant": big.id}
    finally:
        db.close()
