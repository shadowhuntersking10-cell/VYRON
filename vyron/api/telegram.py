"""Telegram Mini App API — initData authentication + admin context.

The Mini App posts the raw initData string; the server verifies the HMAC
against BOT_TOKEN before issuing a normal web session. Admin access is
decided server-side (ADMIN_TELEGRAM_IDS + account role) — the client can
never claim it.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request, Response
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.config import settings
from vyron.db.base import get_db
from vyron.errors import TelegramNotConfiguredError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.sessions import create_session
from vyron.services import telegram_service
from vyron.web.serializers import user_public

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/auth")
def miniapp_auth(
    request: Request,
    response: Response,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
):
    enforce_rate_limit(request, "tg-auth", "20/minute")
    if not settings.telegram_configured:
        raise TelegramNotConfiguredError()
    init_data = str(payload.get("init_data", ""))
    result = telegram_service.authenticate_miniapp(db, init_data)
    user = result["user"]
    create_session(db, user, request, response)
    data = user_public(user)
    data["is_admin"] = result["is_admin"]
    data["is_new"] = result["is_new"]
    data["linked_via_token"] = result["linked_via_token"]
    return ok(data, message_code="TELEGRAM_AUTHENTICATED")


@router.get("/config")
def miniapp_config():
    """Non-secret config the Mini App needs at boot."""
    return ok(
        {
            "telegram_enabled": settings.telegram_configured,
            "public_base_url": settings.public_base_url,
            "miniapp_url": settings.telegram_miniapp_url,
        }
    )
