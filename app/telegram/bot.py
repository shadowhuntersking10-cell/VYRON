"""Telegram bot (aiogram 3): /start with Mini App button, commands, notifications."""
from __future__ import annotations

import asyncio

from app.config import settings
from app.utils.logging import get_logger

log = get_logger("vyron.bot")


def webapp_url() -> str:
    return settings.TELEGRAM_WEBAPP_URL or settings.BASE_URL + "/tg-miniapp"


async def run_bot(stop_event: asyncio.Event) -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set - bot disabled (website still works).")
        await stop_event.wait()
        return
    try:
        from aiogram import Bot, Dispatcher, F
        from aiogram.filters import Command
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
    except Exception as exc:
        log.error("aiogram import failed: %s", exc)
        await stop_event.wait()
        return

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    def open_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🚀 OPEN VYRON", web_app=WebAppInfo(url=webapp_url()))
        ]])

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        # link telegram user server-side
        try:
            from app.database import SessionLocal
            from app import models
            db = SessionLocal()
            try:
                tg = db.query(models.TelegramUser).filter_by(telegram_id=message.from_user.id).first()
                if not tg:
                    tg = models.TelegramUser(
                        telegram_id=message.from_user.id,
                        username=message.from_user.username or "",
                        first_name=message.from_user.first_name or "",
                        last_name=message.from_user.last_name or "",
                        language_code=message.from_user.language_code or "",
                        is_admin=message.from_user.id in settings.admin_telegram_ids,
                    )
                    db.add(tg)
                    db.commit()
            finally:
                db.close()
        except Exception as exc:
            log.error("tg link failed: %s", exc)
        await message.answer("Welcome to VYRON 🎮", reply_markup=open_kb())

    @dp.message(Command("help"))
    async def cmd_help(message: Message):
        await message.answer(
            "VYRON commands:\n/start - open app\n/help - help\n/profile - profile\n"
            "/orders - orders\n/support - support\n/paysupport - payment support",
            reply_markup=open_kb())

    async def _miniapp_reply(message: Message, text: str):
        await message.answer(text, reply_markup=open_kb())

    @dp.message(Command("profile"))
    async def cmd_profile(message: Message):
        await _miniapp_reply(message, "Open your profile 👇")

    @dp.message(Command("orders"))
    async def cmd_orders(message: Message):
        await _miniapp_reply(message, "Open your orders 👇")

    @dp.message(Command("support"))
    async def cmd_support(message: Message):
        await _miniapp_reply(message, "Contact support 👇")

    @dp.message(Command("paysupport"))
    async def cmd_paysupport(message: Message):
        await _miniapp_reply(message, "Payment support 👇")

    async def notifier():
        from app.services.notify import get_outbox
        q = get_outbox()
        while not stop_event.is_set():
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await bot.send_message(msg["telegram_id"], f"🔔 <b>{msg['title']}</b>\n{msg.get('body','')}",
                                       parse_mode="HTML")
            except Exception as exc:
                log.warning("tg notify failed: %s", exc)

    log.info("Telegram bot starting (polling)...")
    notify_task = asyncio.create_task(notifier())
    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    await stop_event.wait()
    polling.cancel()
    notify_task.cancel()
    try:
        await bot.session.close()
    except Exception:
        pass
    log.info("Telegram bot stopped.")
