"""Database engine / session (SQLAlchemy 2, sync). MySQL in production."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine():
    url, is_mysql = settings.effective_database_url()
    if is_mysql:
        return create_engine(
            url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            future=True,
        )
    return create_engine(url, connect_args={"check_same_thread": False}, future=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connectivity() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        url, is_mysql = settings.effective_database_url()
        kind = "MySQL" if is_mysql else "SQLite-dev-fallback"
        return True, f"Database OK ({kind})."
    except Exception as exc:  # noqa: BLE001 - surfaced to operator
        return False, f"Database connection FAILED: {exc}"


def init_db() -> None:
    from app import models  # noqa: F401 - register all models

    Base.metadata.create_all(bind=engine)
