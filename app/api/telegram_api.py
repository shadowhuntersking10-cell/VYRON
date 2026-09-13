"""Telegram Mini App authentication (initData HMAC validation)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.telegram_auth import TelegramAuthError, validate_telegram_init_data
from app.config import settings
from app.database import get_db
from app.schemas import TelegramAuthIn, UserOut
from app.services import auth_service
from app.telegram.notify import link_telegram_user
from app.utils.helpers import client_ip

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/auth", response_model=UserOut)
async def telegram_auth(data: TelegramAuthIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    if not settings.telegram_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "telegram_not_configured")
    try:
        payload = validate_telegram_init_data(
            data.init_data, settings.TELEGRAM_BOT_TOKEN,
            max_age_seconds=settings.TELEGRAM_AUTH_MAX_AGE_SECONDS,
        )
    except TelegramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"telegram_auth_failed:{exc}") from exc
    tg = payload["user"]
    _, user = await link_telegram_user(
        db, telegram_id=int(tg["id"]), username=tg.get("username"),
        first_name=tg.get("first_name"), last_name=tg.get("last_name"),
        language_code=tg.get("language_code"), is_premium=tg.get("is_premium", False),
    )
    token = await auth_service.create_session(db, user, user_agent="telegram-miniapp", ip=client_ip(request.headers))
    await db.commit()
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, token,
        max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        httponly=True, samesite="none" if settings.is_production else "lax",
        secure=settings.is_production, path="/",
    )
    return user
