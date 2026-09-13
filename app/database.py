from __future__ import annotations
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData

from app.config import settings

logger = logging.getLogger(__name__)

# Naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)

class Base(DeclarativeBase):
    metadata = metadata

# Engine
db_url = settings.effective_database_url
engine_kwargs = {
    "echo": settings.is_development and "sqlite" in db_url,
}
if "mysql" in db_url:
    engine_kwargs.update({
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_size": 10,
        "max_overflow": 20,
    })
else:
    # SQLite doesn't support pool_size
    engine_kwargs.update({
        "pool_pre_ping": True,
    })

engine = create_async_engine(db_url, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Create all tables if not exists (for dev / first startup)"""
    from app.models import Base as ModelsBase
    # Import all models to ensure they are registered
    import app.models.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
    logger.info("Database tables ensured")

async def check_db_connection() -> bool:
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection OK: %s", settings.effective_database_url.split("@")[-1])
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        logger.error(f"Effective URL: {settings.effective_database_url}")
        if "mysql" in settings.effective_database_url:
            logger.warning("Falling back? Check MYSQL env vars. If you want dev mode, set DATABASE_URL=sqlite+aiosqlite:///./vyron.db")
        return False
