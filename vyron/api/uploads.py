"""Authenticated image upload (magic-byte validated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.db.models import User
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user
from vyron.services import upload_service

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.post("/image")
async def upload_image(
    request: Request,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "upload", "30/hour", user_id=user.id)
    data = await file.read()
    url = upload_service.store_image(data, folder=f"images/{user.id}")
    return ok({"url": url})
