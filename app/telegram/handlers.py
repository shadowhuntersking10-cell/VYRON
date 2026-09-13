"""aiogram handlers. Uses backend services - no duplicated logic."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from app.config import settings
from app.database import get_session_factory
from app.models import Order, OrderStatus, Payment, PaymentStatus
from app.services.catalog_service import list_games
from app.telegram.keyboards import profile_keyboard, start_keyboard, webapp_url
from app.telegram.notify import link_telegram_user, recent_orders_text

log = logging.getLogger("vyron.bot.handlers")
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
    # Stars payment deep link: /start pay_<order_public_id>
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("pay_"):
        await _send_stars_invoice(message, parts[1][4:])
        return
    text = (
        "Welcome to VYRON 🎮\n\n"
        "Game top-ups, gift cards, marketplace and donations — all in one place.\n"
        "Tap below to open the app:"
    )
    if is_admin:
        text += "\n\n🛠 You are an administrator."
    await message.answer(text, reply_markup=start_keyboard())


async def _send_stars_invoice(message: Message, order_public_id: str) -> None:
    """Send the real Telegram Stars invoice for a pending order payment."""
    from app.payments.stars_provider import stars_for_amount

    factory = get_session_factory()
    async with factory() as db:
        order = (await db.execute(select(Order).where(Order.public_id == order_public_id))).scalars().first()
        if not order:
            await message.answer("Order not found. It may have expired — please create a new one in the app.",
                                 reply_markup=start_keyboard())
            return
        if order.status != OrderStatus.PENDING_PAYMENT:
            await message.answer(f"Order {order.public_id} is already {order.status.value}. No payment needed.",
                                 reply_markup=start_keyboard())
            return
        payment = (await db.execute(select(Payment)
                                    .where(Payment.order_id == order.id, Payment.provider == "stars",
                                           Payment.status == PaymentStatus.PENDING)
                                    .order_by(Payment.id.desc()))).scalars().first()
        title = f"VYRON order {order.public_id}"
        stars = int(((payment.raw_init or {}).get("stars") if payment else None)
                    or stars_for_amount(order.total, order.currency))
        payload = str(payment.id) if payment else f"order:{order.id}"
    desc = f"Total: {order.total} {order.currency} (≈ {stars} ⭐)"
    try:
        assert message.bot is not None and message.from_user is not None
        await message.bot.send_invoice(
            chat_id=message.from_user.id,
            title=title[:32], description=desc[:255],
            payload=f"stars:{payload}", provider_token="",
            currency="XTR", prices=[LabeledPrice(label="Total", amount=stars)],
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("send_invoice failed: %s", exc)
        await message.answer("Couldn't create the Stars invoice. Please try again or use /paysupport.",
                             reply_markup=start_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "VYRON commands:\n"
        "/start — open the app\n"
        "/games — popular games\n"
        "/profile — your profile\n"
        "/orders — recent orders\n"
        "/support — contact support\n"
        "/paysupport — payment problems\n"
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


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    await message.answer(
        "💳 <b>Payment help</b>\n\n"
        "• <b>Stars invoice didn't arrive?</b> Re-open your order in the app and tap Pay again — "
        "you'll get a fresh bot link.\n"
        "• <b>Paid but order still pending?</b> Card/bank confirmations can take a few minutes. "
        "Use /orders to check the status.\n"
        "• <b>Charged twice?</b> Don't worry — open a support ticket from the order page and "
        "we'll refund the duplicate.\n"
        "• <b>Refunds</b> go back to your VYRON wallet instantly once approved.\n\n"
        "Include your order number (VYR-…) when contacting support so we can find it fast.",
        reply_markup=start_keyboard(),
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Approve a Stars invoice only if the underlying payment is still pending."""
    payload = query.invoice_payload or ""
    ok, error = False, "Payment expired or already processed."
    try:
        ref = payload.split("stars:", 1)[1] if payload.startswith("stars:") else ""
        factory = get_session_factory()
        async with factory() as db:
            payment: Payment | None = None
            if ref.startswith("order:"):
                order = await db.get(Order, int(ref.split(":", 1)[1]))
                if order and order.status == OrderStatus.PENDING_PAYMENT:
                    ok = True
            elif ref.isdigit():
                payment = await db.get(Payment, int(ref))
                if payment and payment.status == PaymentStatus.PENDING:
                    if payment.order_id:
                        order = await db.get(Order, payment.order_id)
                        ok = bool(order and order.status == OrderStatus.PENDING_PAYMENT)
                    else:
                        ok = True  # wallet top-up
    except Exception as exc:  # noqa: BLE001
        log.warning("pre_checkout check failed: %s", exc)
    try:
        await query.answer(ok=ok, error_message=None if ok else error)
    except Exception:  # noqa: BLE001
        log.warning("pre_checkout answer failed")


@router.message(F.successful_payment)
async def successful_stars_payment(message: Message) -> None:
    """Settle a paid Stars invoice through the standard payment pipeline."""
    from app.api.webhooks import _settle_paid

    sp = message.successful_payment
    assert sp is not None
    payload = sp.invoice_payload or ""
    ref = payload.split("stars:", 1)[1] if payload.startswith("stars:") else ""
    factory = get_session_factory()
    async with factory() as db:
        payment: Payment | None = None
        if ref.startswith("order:"):
            order = await db.get(Order, int(ref.split(":", 1)[1]))
            if order:
                payment = (await db.execute(select(Payment)
                                            .where(Payment.order_id == order.id, Payment.provider == "stars")
                                            .order_by(Payment.id.desc()))).scalars().first()
                if not payment:
                    from app.payments.manager import get_payment_manager
                    payment = await get_payment_manager().init_payment(
                        db, order, "stars", idempotency_key=f"stars-{order.public_id}")
                    await db.commit()
        elif ref.isdigit():
            payment = await db.get(Payment, int(ref))
        if not payment:
            await message.answer("Payment received, but we couldn't match it to an order. "
                                 "Please contact support with this message.", reply_markup=start_keyboard())
            return
        tg_payment = {"telegram_payment_charge_id": sp.telegram_payment_charge_id,
                      "provider_payment_charge_id": sp.provider_payment_charge_id,
                      "total_stars": sp.total_amount, "currency": sp.currency,
                      "invoice_payload": payload}
        await _settle_paid(db, payment, sp.telegram_payment_charge_id, tg_payment)
        await db.commit()
    await message.answer("✅ Payment confirmed! Your order is being processed. Use /orders to track it.",
                         reply_markup=start_keyboard())
