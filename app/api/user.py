from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import UserOut
from app.services import auth_service

router = APIRouter(prefix="/api/user", tags=["user"])


class ProfileIn(BaseModel):
    full_name: str | None = None
    username: str | None = None
    lang: str | None = None
    theme: str | None = None
    avatar_url: str | None = None


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.patch("/profile", response_model=UserOut)
async def update_profile(data: ProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.full_name is not None:
        user.full_name = data.full_name[:255]
    if data.username is not None:
        user.username = data.username[:64]
    if data.lang in ("uz", "en", "ru"):
        user.lang = data.lang
    if data.theme in ("light", "dark", "system"):
        user.theme = data.theme
    if data.avatar_url is not None:
        user.avatar_url = data.avatar_url[:512]
    await db.commit()
    return user


@router.post("/password")
async def change_password(data: PasswordIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(400, "password_too_short")
    try:
        await auth_service.change_password(db, user, data.old_password, data.new_password)
        await db.commit()
    except auth_service.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True}
