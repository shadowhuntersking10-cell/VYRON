"""Pytest fixtures: isolated SQLite test DB + ASGI client."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

TEST_DB = "./test_vyron.db"

if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

from app.api.app import create_app  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.database import get_db  # noqa: E402
from app.models import Game, Product, Supplier, User, UserRole  # noqa: E402
from app.models.base import Base  # noqa: E402

engine = create_async_engine(f"sqlite+aiosqlite:///{TEST_DB}")
TestSession = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with TestSession() as session:
        yield session


def _build_client() -> AsyncClient:
    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest_asyncio.fixture()
async def db():
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def client():
    async with _build_client() as c:
        yield c


def _uid() -> str:
    return uuid.uuid4().hex[:8]


async def make_user(db, email: str | None = None, role=UserRole.USER, password="Password123") -> User:
    tag = _uid()
    email = email or f"u{tag}@vyronmail.com"
    # ensure unique even if caller reuses an address across runs
    local, _, domain = email.partition("@")
    email = f"{local}+{tag}@{domain or 'vyronmail.com'}"
    u = User(email=email, username=f"{local[:40]}{tag}", password_hash=hash_password(password), role=role)
    db.add(u)
    await db.commit()
    await db.refresh(u)
    # stash the effective email for login helpers
    u.effective_email = email  # type: ignore[attr-defined]
    return u


async def make_catalog(db) -> tuple[Supplier, Game, Product]:
    tag = _uid()
    s = Supplier(code=f"manual-{tag}", name="Manual", status="ACTIVE")
    db.add(s)
    await db.flush()
    g = Game(slug=f"test-game-{tag}", title="Test Game", fields_schema=[], supplier_id=s.id)
    db.add(g)
    await db.flush()
    p = Product(game_id=g.id, name="100 Coins", supplier_id=s.id, supplier_cost=80,
                selling_price=100, currency="UZS")
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return s, g, p


async def login(client: AsyncClient, email: str, password: str = "Password123"):
    r = await client.post("/api/auth/login", json={"login": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()
