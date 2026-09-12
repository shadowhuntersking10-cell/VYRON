"""Global search API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.services import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = Query("", max_length=80),
    page: int = Query(1, ge=1),
    db: DbSession = Depends(get_db),
):
    data = search_service.global_search(db, q, page=page)
    return ok(data)
