"""Pagination helpers for API + admin listings."""
from __future__ import annotations

from typing import TypeVar

from sqlalchemy import func, select

T = TypeVar("T")


def pagination_params(page: int = 1, per_page: int = 20) -> tuple[int, int]:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 20)))
    return page, per_page


async def paginate_query(session, stmt, page: int = 1, per_page: int = 20) -> dict:
    page, per_page = pagination_params(page, per_page)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar() or 0
    rows = (await session.execute(stmt.offset((page - 1) * per_page).limit(per_page))).scalars().all()
    pages = max(1, (total + per_page - 1) // per_page)
    return {"items": rows, "total": total, "page": page, "per_page": per_page, "pages": pages}
