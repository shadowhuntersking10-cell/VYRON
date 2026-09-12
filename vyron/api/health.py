"""Health & readiness endpoints (no auth, no secrets)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import get_db

VERSION = "1.0.0"

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "vyron", "version": VERSION}


@router.get("/ready")
def ready(db: DbSession = Depends(get_db)):
    checks: Dict[str, Any] = {}
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    checks["database"] = "ok" if db_ok else "error"

    redis_ok = False
    try:
        from vyron.redis_client import redis_ping

        redis_ok = redis_ping()
    except Exception:
        redis_ok = False
    checks["redis"] = "ok" if redis_ok else "error"

    status_code = 200 if (db_ok and redis_ok) else 503
    return JSONResponse({"status": "ready" if status_code == 200 else "degraded", "version": VERSION, "checks": checks}, status_code=status_code)
