"""Bot keyboards incl. the big Web App button."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings


def webapp_url(path: str = "") -> str:
    base = (settings.TELEGRAM_WEBAPP_URL or settings.APP_BASE_URL + "/miniapp").rstrip("/")
    return f"{base}{path}"


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open VYRON", web_app=WebAppInfo(url=webapp_url()))],
        [
            InlineKeyboardButton(text="🎮 Games", web_app=WebAppInfo(url=webapp_url("?tab=games"))),
            InlineKeyboardButton(text="🧾 Orders", web_app=WebAppInfo(url=webapp_url("?tab=orders"))),
        ],
        [InlineKeyboardButton(text="🆘 Support", callback_data="support")],
    ])


def profile_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🚀 Open VYRON", web_app=WebAppInfo(url=webapp_url("?tab=profile")))],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Admin Panel", web_app=WebAppInfo(url=webapp_url("?tab=admin")))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
