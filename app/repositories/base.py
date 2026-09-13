"""Generic async repository to keep DB access consistent."""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id_: int) -> T | None:
        return await self.session.get(self.model, id_)

    async def get_by(self, **filters) -> T | None:
        stmt = select(self.model).filter_by(**filters).limit(1)
        return (await self.session.execute(stmt)).scalars().first()

    async def list(self, *, limit: int = 50, offset: int = 0, **filters) -> list[T]:
        stmt = select(self.model).filter_by(**filters).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add(self, obj: T) -> T:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: T) -> None:
        await self.session.delete(obj)
        await self.session.flush()
