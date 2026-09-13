"""aiogram handlers. Uses backend services - no duplicated logic."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.config import settings
from app.database import get_session_factory
from app.services.catalog_service import list_games
from app.telegram.keyboards import profile_keyboard, start_keyboard, webapp_url
from app.telegram.notify import link_telegram_user, recent_orders_text

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg = message.from_user
    assert tg is not None
    factory = get_session_factory()
    async with factory() as db:
        await link_telegram_user(db, telegram_id=tg.id, username=tg.username,
                                 first_name=tg.first_name, last_name=tg.last_name,
                                 language_code=tg.language_code, is_premium=bool(tg.is_premium))
        await db.commit()
    is_admin = tg.id in settings.admin_telegram_ids
    text = (
        "Welcome to VYRON 🎮\n\n"
        "Game top-ups, gift cards, marketplace and donations — all in one place.\n"
        "Tap below to open the app:"
    )
    if is_admin:
        text += "\n\n🛠 You are an administrator."
    await message.answer(text, reply_markup=start_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "VYRON commands:\n"
        "/start — open the app\n"
        "/games — popular games\n"
        "/profile — your profile\n"
        "/orders — recent orders\n"
        "/support — contact support\n"
        "/help — this message",
        reply_markup=start_keyboard(),
    )


@router.message(Command("games"))
async def cmd_games(message: Message) -> None:
    factory = get_session_factory()
    async with factory() as db:
        games = await list_games(db)
    if not games:
        await message.answer("No games yet. Check back soon!", reply_markup=start_keyboard())
        return
    lines = ["🎮 Popular games:"] + [f"• {g.title}" for g in games[:10]]
    lines.append(f'\nOpen the app to top up: {webapp_url("?tab=games")}')
    await message.answer("\n".join(lines), reply_markup=start_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    tg = message.from_user
    assert tg is not None
    is_admin = tg.id in settings.admin_telegram_ids
    await message.answer(
        f"👤 {tg.first_name or 'Player'}\nID: <code>{tg.id}</code>\n"
        f"Role: {'ADMIN 🛠' if is_admin else 'USER'}\n\nOpen VYRON to manage your account:",
        reply_markup=profile_keyboard(is_admin),
    )


@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    tg = message.from_user
    assert tg is not None
    factory = get_session_factory()
    async with factory() as db:
        text = await recent_orders_text(db, tg.id)
    await message.answer(text, reply_markup=start_keyboard())


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    await message.answer(
        "🆘 Need help? Open a support ticket in the app and our team will reply soon.",
        reply_markup=start_keyboard(),
    )


@router.callback_query(F.data == "support")
async def cb_support(query: CallbackQuery) -> None:
    if query.message:
        await query.message.answer("🆘 Open support in the VYRON app:", reply_markup=start_keyboard())
    await query.answer()
