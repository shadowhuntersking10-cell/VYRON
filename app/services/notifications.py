"""Customer notifications: in-app + Telegram (when configured)."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.i18n import t
from app.logging_config import get_logger
from app.models import Notification, User

log = get_logger("vyron.notifications")


def push_notification(
    session: Session,
    user: User,
    *,
    kind: str,
    title_key: str,
    body_key: str,
    params: Optional[dict[str, Any]] = None,
) -> Notification:
    note = Notification(
        user_id=user.id,
        kind=kind,
        title_key=title_key,
        body_key=body_key,
        params=params,
    )
    session.add(note)
    return note


async def send_telegram(user: User, text: str) -> None:
    """Best-effort Telegram delivery. Requires TELEGRAM_BOT_TOKEN + user link."""
    settings = get_settings()
    if not settings.telegram_configured() or not user.telegram_id:
        return
    try:
        import httpx

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                json={
                    "chat_id": user.telegram_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:  # never break order flow on notification errors
        log.warning("Telegram notify failed: %s", type(exc).__name__)


def notify_user(
    session: Session,
    user: User,
    *,
    kind: str,
    title_key: str,
    body_key: str,
    params: Optional[dict[str, Any]] = None,
) -> None:
    push_notification(
        session, user, kind=kind, title_key=title_key, body_key=body_key, params=params
    )
    lang = user.language or "uz"
    params = params or {}
    title = t(title_key, lang)
    body = t(body_key, lang, **params)
    lines = [f"VYRON — {title}", body]
    if "order_number" in params:
        lines.append(f"{t('order_number', lang)}: {params['order_number']}")
    if "status" in params:
        lines.append(f"{t('status', lang)}: {params['status']}")
    if "total" in params:
        lines.append(f"{t('total', lang)}: {params['total']} {params.get('currency', '')}")
    # fire-and-forget from event loop when available
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(send_telegram(user, "\n".join(lines)))
    except RuntimeError:
        pass
