"""Shared API dependencies and response helpers."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import Query


def ok(data: Any = None, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def paginated(items: list, total: int, page: int, page_size: int) -> Dict[str, Any]:
    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    )


PaginationParams = Dict[str, int]


def pagination(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> PaginationParams:
    return {"page": page, "page_size": page_size}
