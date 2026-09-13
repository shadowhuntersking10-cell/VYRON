"""Telegram account linking + push delivery used by notification_service."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Order, TelegramUser, User, UserRole
from app.utils.helpers import utcnow

log = logging.getLogger("vyron.telegram")


async def link_telegram_user(
    db: AsyncSession, *, telegram_id: int, username=None, first_name=None,
    last_name=None, language_code=None, is_premium=False,
) -> tuple[TelegramUser, User]:
    tg = (await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))).scalars().first()
    user: User | None = None
    if tg and tg.user_id:
        user = await db.get(User, tg.user_id)
    if user is None:
        # New Telegram user -> create a VYRON account automatically
        base = (username or f"tg{telegram_id}")[:60]
        user = User(username=base, full_name=" ".join(x for x in [first_name, last_name] if x) or None,
                    lang=(language_code or "uz")[:8] if (language_code or "")[:2] in ("uz", "en", "ru") else "uz")
        if telegram_id in settings.admin_telegram_ids:
            user.role = UserRole.ADMIN
        db.add(user)
        await db.flush()
    else:
        # Elevate to admin if listed in ADMIN_TELEGRAM_IDS
        if telegram_id in settings.admin_telegram_ids and user.role != UserRole.ADMIN:
            user.role = UserRole.ADMIN
    if tg is None:
        tg = TelegramUser(telegram_id=telegram_id, user_id=user.id)
        db.add(tg)
    tg.user_id = user.id
    tg.username = username
    tg.first_name = first_name
    tg.last_name = last_name
    tg.language_code = language_code
    tg.is_premium = bool(is_premium)
    tg.last_auth_at = utcnow()
    await db.flush()
    return tg, user


async def telegram_id_for_user(db: AsyncSession, user_id: int) -> int | None:
    row = (await db.execute(select(TelegramUser).where(TelegramUser.user_id == user_id).limit(1))).scalars().first()
    return row.telegram_id if row else None


async def recent_orders_text(db: AsyncSession, telegram_id: int) -> str:
    tg = (await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))).scalars().first()
    if not tg or not tg.user_id:
        return "You have no VYRON account yet. Press /start first."
    orders = (await db.execute(
        select(Order).where(Order.user_id == tg.user_id).order_by(Order.id.desc()).limit(5)
    )).scalars().all()
    if not orders:
        return "You have no orders yet. Open VYRON to top up your favourite game 🎮"
    lines = ["🧾 Your recent orders:"]
    for o in orders:
        lines.append(f"• {o.public_id} — {o.total} {o.currency} — {o.status.value}")
    return "\n".join(lines)
