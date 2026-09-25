"""VYRON Telegram bot.

/start -> Web App button that opens the VYRON webapp.
Admin IDs (TELEGRAM_ADMIN_IDS) get the admin entry. 3 languages.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.i18n import normalize_lang
from app.logging_config import get_logger
from app.models import Role, RoleName, TelegramUser, User

log = get_logger("vyron.bot")

WELCOME = {
    "uz": (
        "VYRON — raqamli o'yin bozori 🎮\n\n"
        "O'yin valyutasi, to'ldirish va raqamli mahsulotlar.\n"
        "WebApp orqali xarid qiling — tez va xavfsiz."
    ),
    "en": (
        "VYRON — digital gaming marketplace 🎮\n\n"
        "Game currency, top-ups and digital products.\n"
        "Shop via the WebApp — fast and secure."
    ),
    "ru": (
        "VYRON — цифровой игровой маркетплейс 🎮\n\n"
        "Игровая валюта, пополнения и цифровые продукты.\n"
        "Покупайте через WebApp — быстро и безопасно.",
    ),
}

OPEN_BTN = {"uz": "🛍 VYRON ochish", "en": "🛍 Open VYRON", "ru": "🛍 Открыть VYRON"}
ADMIN_BTN = {"uz": "⚙️ Admin panel", "en": "⚙️ Admin panel", "ru": "⚙️ Админ панель"}
HELP_TEXT = {
    "uz": (
        "Yordam:\n"
        "/start — VYRON webapp\n"
        "/lang — tilni tanlash\n"
        "/orders — buyurtmalaringiz\n"
        "Savollar uchun: /support"
    ),
    "en": (
        "Help:\n"
        "/start — VYRON webapp\n"
        "/lang — choose language\n"
        "/orders — your orders\n"
        "Questions: /support"
    ),
    "ru": (
        "Помощь:\n"
        "/start — VYRON webapp\n"
        "/lang — выбор языка\n"
        "/orders — ваши заказы\n"
        "Вопросы: /support"
    ),
}
LANG_PROMPT = {
    "uz": "Tilni tanlang:",
    "en": "Choose language:",
    "ru": "Выберите язык:",
}


def _webapp_url() -> str:
    settings = get_settings()
    return settings.webapp_url or settings.public_base_url or "https://t.me"


async def run_bot() -> None:
    """Run the aiogram bot. Safe no-op when TELEGRAM_BOT_TOKEN is absent."""
    settings = get_settings()
    if not settings.telegram_configured():
        log.info("Telegram bot NOT CONFIGURED (TELEGRAM_BOT_TOKEN empty) — bot disabled")
        return

    import asyncio

    from aiogram import Bot, Dispatcher, F
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.filters import Command, CommandStart
    from aiogram.types import (
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        KeyboardButton,
        Message,
        ReplyKeyboardMarkup,
        WebAppInfo,
    )

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    def _lang_of(message: Message) -> str:
        return normalize_lang(message.from_user.language_code if message.from_user else None)

    def _sync_user(message: Message) -> str:
        """Persist telegram user + link admins. Returns language."""
        tg = message.from_user
        lang = normalize_lang(tg.language_code if tg else None)
        with session_scope() as session:
            row = session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == tg.id)
            ).scalar_one_or_none()
            if row is None:
                row = TelegramUser(telegram_id=tg.id)
                session.add(row)
            row.username = tg.username
            row.first_name = tg.first_name
            row.language = lang
            user = session.execute(
                select(User).where(User.telegram_id == tg.id)
            ).scalar_one_or_none()
            is_admin = tg.id in settings.telegram_admin_ids
            if user is None:
                role_name = RoleName.ADMIN if is_admin else RoleName.CUSTOMER
                role = session.execute(
                    select(Role).where(Role.name == role_name)
                ).scalar_one()
                base = (tg.username or f"tg{tg.id}")[:28]
                candidate = base
                i = 1
                from sqlalchemy import func as sa_func

                while session.execute(
                    select(User).where(User.username == candidate)
                ).scalar_one_or_none():
                    candidate = f"{base}{i}"
                    i += 1
                user = User(
                    username=candidate,
                    telegram_id=tg.id,
                    role_id=role.id,
                    language=lang,
                )
                session.add(user)
                session.flush()
            elif is_admin and not user.is_admin:
                role = session.execute(
                    select(Role).where(Role.name == RoleName.ADMIN)
                ).scalar_one()
                user.role_id = role.id
            row.user_id = user.id
            lang = user.language or lang
        return lang

    @dp.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        lang = _sync_user(message)
        is_admin = (
            message.from_user
            and message.from_user.id in settings.telegram_admin_ids
        )
        buttons: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton(
                    text=OPEN_BTN[lang],
                    web_app=WebAppInfo(url=_webapp_url()),
                )
            ]
        ]
        if is_admin:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=ADMIN_BTN[lang],
                        web_app=WebAppInfo(url=f"{_webapp_url()}#/admin"),
                    )
                ]
            )
        buttons.append(
            [
                InlineKeyboardButton(text="🇺🇿 UZ", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇬🇧 EN", callback_data="lang:en"),
                InlineKeyboardButton(text="🇷🇺 RU", callback_data="lang:ru"),
            ]
        )
        await message.answer(WELCOME[lang], reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    @dp.message(Command("lang"))
    async def cmd_lang(message: Message) -> None:
        lang = _lang_of(message)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
                    InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
                    InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                ]
            ]
        )
        await message.answer(LANG_PROMPT[lang], reply_markup=kb)

    @dp.callback_query(F.data.startswith("lang:"))
    async def cb_lang(callback) -> None:
        lang = normalize_lang(callback.data.split(":", 1)[1])
        with session_scope() as session:
            row = session.execute(
                select(TelegramUser).where(TelegramUser.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()
            if row:
                row.language = lang
            user = session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            ).scalar_one_or_none()
            if user:
                user.language = lang
        await callback.answer(LANG_PROMPT[lang])
        await callback.message.answer(WELCOME[lang])

    @dp.message(Command("help", "support"))
    async def cmd_help(message: Message) -> None:
        lang = _sync_user(message)
        await message.answer(HELP_TEXT[lang])

    @dp.message(Command("orders"))
    async def cmd_orders(message: Message) -> None:
        lang = _sync_user(message)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=OPEN_BTN[lang], web_app=WebAppInfo(url=f"{_webapp_url()}#/account"))]
            ]
        )
        await message.answer(WELCOME[lang], reply_markup=kb)

    @dp.message(Command("admin"))
    async def cmd_admin(message: Message) -> None:
        lang = _sync_user(message)
        if not message.from_user or message.from_user.id not in settings.telegram_admin_ids:
            await message.answer("⛔️" if lang == "uz" else "⛔️")
            return
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=ADMIN_BTN[lang],
                        web_app=WebAppInfo(url=f"{_webapp_url()}#/admin"),
                    )
                ]
            ]
        )
        await message.answer("VYRON Admin", reply_markup=kb)

    log.info("Telegram bot starting (polling)...")
    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        log.info("Telegram bot stopped")
        raise
    except Exception as exc:
        log.error("Telegram bot crashed: %s", type(exc).__name__)
