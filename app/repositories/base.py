"""Generic repository."""
from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, db: Session, model: type[T]):
        self.db = db
        self.model = model

    def get(self, id_: int) -> T | None:
        return self.db.get(self.model, id_)

    def list(self, page: int = 1, per_page: int = 20, **filters) -> tuple[list[T], int]:
        q = self.db.query(self.model)
        for k, v in filters.items():
            if v is not None and hasattr(self.model, k):
                q = q.filter(getattr(self.model, k) == v)
        total = q.count()
        items = q.offset((page - 1) * per_page).limit(per_page).all()
        return items, total

    def add(self, obj: T) -> T:
        self.db.add(obj)
        self.db.flush()
        return obj
