"""Bot command handlers. All account decisions are made server-side:
- identity comes from the Telegram update (bot API verified),
- linkage via one-time TelegramLinkToken issued from the web dashboard,
- admin access via ADMIN_TELEGRAM_IDS or the linked account's role."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from vyron.config import settings
from vyron.db.base import get_session_factory
from vyron.db.models import Order, TelegramConnection, User
from vyron.errors import VyronError
from vyron.i18n import normalize_lang, t
from vyron.logging import get_logger
from vyron.services import auth_service, telegram_service

log = get_logger("vyron.telegram_bot")


def _session():
    return get_session_factory()()


def _context_user(db, telegram_id: int) -> tuple[Optional[TelegramConnection], Optional[User]]:
    connection = db.scalar(select(TelegramConnection).where(TelegramConnection.telegram_id == telegram_id))
    user = db.get(User, connection.user_id) if connection else None
    return connection, user


def _lang(user: Optional[User]) -> str:
    return normalize_lang(user.locale if user else "")


def _open_button(label: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=settings.miniapp_url))


def _admin_keyboard(db, user: Optional[User], telegram_id: int, lang: str) -> list:
    if telegram_service.is_admin_context(db, user, telegram_id):
        return [InlineKeyboardButton(f"🛡️ {t('bot.admin_panel', lang)}", url=f"{settings.public_base_url.rstrip('/')}/admin")]
    return []


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tg_user = update.effective_user
    if tg_user is None:
        return
    args = context.args or []
    db = _session()
    try:
        connection, user = _context_user(db, tg_user.id)

        # /start <one-time-link-token> — account linking flow
        if args:
            token = args[0].strip()
            try:
                target = auth_service.consume_telegram_link_token(db, token)
                telegram_service.link_account(db, target, _tg_user_adapter(tg_user))
                lang = _lang(target)
                await update.message.reply_text(
                    f"✅ {t('bot.link_success', lang, name=target.name or target.username)}",
                    reply_markup=_main_keyboard(db, target, tg_user.id, lang),
                )
                return
            except VyronError as exc:
                lang = _lang(user)
                await update.message.reply_text(f"⚠️ {exc!s}")
                return

        if user is None:
            # Not linked yet — guest welcome; the Mini App provisions/links via initData.
            lang = "uz"
            await update.message.reply_text(
                t("bot.welcome_guest", lang),
                reply_markup=_main_keyboard(db, None, tg_user.id, lang),
                parse_mode=ParseMode.HTML,
            )
            return

        lang = _lang(user)
        await update.message.reply_text(
            t("bot.welcome", lang, name=user.name or user.username),
            reply_markup=_main_keyboard(db, user, tg_user.id, lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        db.rollback()
        log.error("bot /start failed", error=str(exc))
        await update.message.reply_text(t("errors.INTERNAL_ERROR", "en"))
    finally:
        db.close()


def _tg_user_adapter(tg_user):
    from vyron.security.telegram_auth import TelegramUser

    return TelegramUser(
        id=tg_user.id,
        first_name=tg_user.first_name or "",
        last_name=tg_user.last_name or "",
        username=tg_user.username or "",
        language_code=tg_user.language_code or "",
        is_premium=bool(getattr(tg_user, "is_premium", False)),
    )


def _main_keyboard(db, user: Optional[User], telegram_id: int, lang: str) -> InlineKeyboardMarkup:
    rows = [[_open_button(f"🚀 {t('bot.open_app', lang)}")]]
    admin_row = _admin_keyboard(db, user, telegram_id, lang)
    if admin_row:
        rows.append(admin_row)
    return InlineKeyboardMarkup(rows)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _session()
    try:
        _, user = _context_user(db, update.effective_user.id)
        lang = _lang(user)
        await update.message.reply_text(
            t("bot.help_body", lang),
            reply_markup=_main_keyboard(db, user, update.effective_user.id, lang),
        )
    finally:
        db.close()


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _session()
    try:
        _, user = _context_user(db, update.effective_user.id)
        if user is None:
            await _reply_not_linked(update, db)
            return
        lang = _lang(user)
        orders = db.scalars(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(5)
        ).all()
        if not orders:
            await update.message.reply_text(
                t("bot.no_orders", lang),
                reply_markup=_main_keyboard(db, user, update.effective_user.id, lang),
            )
            return
        lines = [f"<b>{t('bot.orders_title', lang)}</b>", ""]
        for o in orders:
            lines.append(f"<code>{o.number}</code> — {o.status} — {o.total} {o.currency}")
        await update.message.reply_html(
            "\n".join(lines),
            reply_markup=_main_keyboard(db, user, update.effective_user.id, lang),
        )
    except Exception as exc:
        log.error("bot /orders failed", error=str(exc))
    finally:
        db.close()


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _session()
    try:
        _, user = _context_user(db, update.effective_user.id)
        if user is None:
            await _reply_not_linked(update, db)
            return
        lang = _lang(user)
        order_count = db.scalar(select(func.count(Order.id)).where(Order.user_id == user.id)) or 0
        is_admin = telegram_service.is_admin_context(db, user, update.effective_user.id)
        text = (
            f"<b>{t('bot.profile_title', lang)}</b>\n\n"
            f"👤 {user.name or user.username}\n"
            f"@{user.username}\n"
            f"📧 {user.email}\n"
            f"🎖 {user.role}"
            + ("  🛡" if is_admin else "")
            + f"\n📦 {t('bot.orders_count', lang)}: {order_count}"
        )
        await update.message.reply_html(text, reply_markup=_main_keyboard(db, user, update.effective_user.id, lang))
    except Exception as exc:
        log.error("bot /profile failed", error=str(exc))
    finally:
        db.close()


async def cmd_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _session()
    try:
        _, user = _context_user(db, update.effective_user.id)
        lang = _lang(user)
        rows = [[_open_button(f"🚀 {t('bot.open_app', lang)}")]]
        rows.append([InlineKeyboardButton(f"🎧 {t('nav.support', lang)}", url=f"{settings.public_base_url.rstrip('/')}/support")])
        await update.message.reply_text(t("bot.support_body", lang), reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


async def _reply_not_linked(update: Update, db) -> None:
    lang = "uz"
    await update.message.reply_text(
        f"{t('bot.not_linked', lang)}\n\n{t('telegram_page.link_instructions', lang)}",
        reply_markup=InlineKeyboardMarkup([[_open_button(f"🚀 {t('bot.open_app', lang)}")]]),
    )


async def on_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is None:
        return
    db = _session()
    try:
        _, user = _context_user(db, update.effective_user.id)
        lang = _lang(user)
        await update.message.reply_text(t("bot.unknown", lang))
    finally:
        db.close()


async def post_init(application) -> None:
    from telegram import BotCommand

    try:
        await application.bot.set_my_commands([
            BotCommand("start", "Start / Бошлаш"),
            BotCommand("help", "Help / Ёрдам"),
            BotCommand("orders", "Orders / Буюртмалар"),
            BotCommand("profile", "Profile / Профил"),
            BotCommand("support", "Support / Қўллаб-қувватлаш"),
        ])
        me = await application.bot.get_me()
        log.info("telegram bot online", username=me.username)
    except Exception as exc:
        log.warning("post_init failed", error=str(exc))
