"""In-app notifications + Telegram push fan-out."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification

log = logging.getLogger("vyron.notifications")

# Telegram delivery is best-effort and async; the bot module registers a sender.
_telegram_sender = None


def register_telegram_sender(fn) -> None:
    global _telegram_sender
    _telegram_sender = fn


async def notify_user(
    db: AsyncSession,
    *,
    user_id: int,
    kind: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    push_telegram: bool = True,
) -> Notification:
    note = Notification(user_id=user_id, kind=kind, title=title, body=body, link=link)
    db.add(note)
    await db.flush()
    if push_telegram and _telegram_sender is not None:
        try:
            ok = await _telegram_sender(user_id, title, body or "", link)
            note.sent_telegram = bool(ok)
            await db.flush()
        except Exception as exc:  # noqa: BLE001 - push must never break the flow
            log.warning("telegram push failed for user %s: %s", user_id, exc)
    return note


async def notify_order_event(db: AsyncSession, *, user_id: int | None, title: str, body: str, link: str | None = None) -> None:
    if not user_id:
        return
    await notify_user(db, user_id=user_id, kind="order", title=title, body=body, link=link)
