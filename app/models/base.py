"""Declarative base + shared mixins."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Client-side onupdate (not func.now()): server-side ON UPDATE expires
    # the attribute after flush, which cannot be lazily reloaded in async
    # SQLAlchemy (MissingGreenlet) when the row is serialized afterwards.
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        default=_utcnow, onupdate=_utcnow, nullable=False,
    )
