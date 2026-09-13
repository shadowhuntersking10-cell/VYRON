"""Database engine, sessions, helpers. MySQL primary, SQLite dev/test fallback."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

log = logging.getLogger("vyron.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    return settings.effective_database_url


def init_engine(database_url: str | None = None) -> AsyncEngine:
    """Create (or reuse) the async engine for the given URL."""
    global _engine, _session_factory
    url = database_url or get_database_url()
    if _engine is not None:
        return _engine
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    _engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    log.info("DB engine initialised (mysql=%s)", url.startswith("mysql"))
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_connection() -> tuple[bool, str]:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - surfaced to startup banner
        return False, f"{type(exc).__name__}: {exc}"


async def create_all_tables() -> None:
    """Create all tables (used when Alembic migrations were not applied)."""
    from app.models import Base  # noqa: PLC0415 - avoid circular import

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Ensured all tables exist")


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
