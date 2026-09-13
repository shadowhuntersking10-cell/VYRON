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


async def ensure_schema() -> list[str]:
    """Idempotent startup migration: add columns that exist in models but
    not in the database (for deployments created before a model change).

    Production MySQL deployments should prefer `alembic upgrade head`;
    this is a safety net that never drops or alters existing data.
    Returns the list of added `table.column` names.
    """
    from sqlalchemy import inspect  # noqa: PLC0415

    from app.models import Base  # noqa: PLC0415

    engine = get_engine()
    applied: list[str] = []

    def _run(sync_conn) -> None:
        inspector = inspect(sync_conn)
        existing_tables = set(inspector.get_table_names())
        dialect = sync_conn.dialect
        for table in Base.metadata.tables.values():
            if table.name not in existing_tables:
                table.create(bind=sync_conn)
                applied.append(f"{table.name}.*")
                continue
            present = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                coltype = column.type.compile(dialect=dialect)
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}"
                default = None
                if column.server_default is not None:
                    default = str(column.server_default.arg)
                elif column.default is not None and column.default.arg is not None:
                    arg = column.default.arg
                    default = f"'{arg}'" if isinstance(arg, str) else str(arg)
                # Never add a bare NOT NULL column to a non-empty table.
                if not column.nullable and default is None:
                    ddl += " NULL"
                elif default is not None:
                    if dialect.name == "mysql" and isinstance(default, str) and default.upper() in (
                        "CURRENT_TIMESTAMP", "NOW()"):
                        ddl += f" DEFAULT {default}"
                    else:
                        ddl += f" DEFAULT {default}"
                try:
                    sync_conn.exec_driver_sql(ddl)
                    applied.append(f"{table.name}.{column.name}")
                except Exception as exc:  # noqa: BLE001 - log and continue
                    log.warning("ensure_schema skipped %s.%s: %s", table.name, column.name, exc)

    async with engine.begin() as conn:
        await conn.run_sync(_run)
    if applied:
        log.info("ensure_schema added %d columns: %s", len(applied), ", ".join(applied))
    return applied


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
