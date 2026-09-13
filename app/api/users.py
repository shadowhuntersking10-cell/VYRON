from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import User

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "avatar_url": current_user.avatar_url,
        "is_verified": current_user.is_verified,
        "is_admin": current_user.is_admin,
        "language": current_user.language,
        "theme": current_user.theme,
        "status": current_user.status,
        "created_at": current_user.created_at.isoformat()
    }

@router.put("/me")
async def update_me(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if "display_name" in payload:
        current_user.display_name = payload["display_name"][:100]
    if "language" in payload and payload["language"] in ("uz", "ru", "en"):
        current_user.language = payload["language"]
    if "theme" in payload and payload["theme"] in ("light", "dark", "system"):
        current_user.theme = payload["theme"]
    if "avatar_url" in payload:
        current_user.avatar_url = payload["avatar_url"]

    await db.commit()
    await db.refresh(current_user)

    return {"success": True, "user": {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "language": current_user.language,
        "theme": current_user.theme
    }}

@router.get("/settings")
async def get_settings(current_user: User = Depends(get_current_user)):
    return {
        "language": current_user.language,
        "theme": current_user.theme,
        "notifications": True
    }
