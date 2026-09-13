"""In-app notifications + Telegram outbox queue."""
from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from app import models

_outbox: asyncio.Queue | None = None


def get_outbox() -> asyncio.Queue:
    global _outbox
    if _outbox is None:
        _outbox = asyncio.Queue()
    return _outbox


def create(db: Session, user_id: int, kind: str, title: str, body: str = "", link: str = "") -> models.Notification:
    n = models.Notification(user_id=user_id, kind=kind, title=title, body=body, link=link)
    db.add(n)
    db.flush()
    # enqueue telegram push (best effort)
    try:
        tg = db.query(models.TelegramUser).filter_by(user_id=user_id).first()
        if tg:
            q = get_outbox()
            try:
                q.put_nowait({"telegram_id": tg.telegram_id, "title": title, "body": body})
            except Exception:
                pass
    except Exception:
        pass
    return n
