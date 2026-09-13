"""Telegram Bot service (aiogram v3, long polling). Started from main.py."""
from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.database import get_session_factory
from app.services.notification_service import register_telegram_sender
from app.telegram.handlers import router as handlers_router
from app.telegram.notify import telegram_id_for_user

log = logging.getLogger("vyron.bot")


class TelegramBotService:
    def __init__(self) -> None:
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.bot: Bot | None = None
        self.dp = Dispatcher()
        self.dp.include_router(handlers_router)
        self._task: asyncio.Task | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    async def _push(self, user_id: int, title: str, body: str, link: str | None) -> bool:
        if not self.bot:
            return False
        factory = get_session_factory()
        async with factory() as db:
            chat_id = await telegram_id_for_user(db, user_id)
        if not chat_id:
            return False
        text = f"<b>{html.escape(title)}</b>"
        if body:
            text += f"\n{html.escape(body[:800])}"
        if link:
            url = link if link.startswith("http") else settings.APP_BASE_URL.rstrip("/") + link
            text += f'\n<a href="{html.escape(url)}">Open VYRON</a>'
        try:
            await self.bot.send_message(chat_id, text)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram send failed: %s", exc)
            return False

    async def start(self) -> None:
        if not self.enabled:
            log.warning("TELEGRAM_BOT_TOKEN not set - bot disabled (Mini App still works via initData)")
            return
        self.bot = Bot(token=self.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        register_telegram_sender(self._push)
        self._task = asyncio.create_task(self.dp.start_polling(self.bot, handle_signals=False))
        me = await self.bot.get_me()
        log.info("Telegram bot started as @%s", me.username)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self.bot:
            await self.bot.session.close()
            self.bot = None
        log.info("Telegram bot stopped")


_service: TelegramBotService | None = None


def get_bot_service() -> TelegramBotService:
    global _service
    if _service is None:
        _service = TelegramBotService()
    return _service
