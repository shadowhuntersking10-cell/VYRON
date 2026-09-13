from __future__ import annotations
import logging
import asyncio
from typing import Optional
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from app.config import settings

logger = logging.getLogger(__name__)

class TelegramBotService:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self._running = False

    async def init_bot(self):
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram bot token not configured, bot disabled")
            return False

        try:
            self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            self.dp = Dispatcher()

            # Register handlers
            self.dp.message.register(self.cmd_start, Command("start"))
            self.dp.message.register(self.cmd_help, Command("help"))
            self.dp.message.register(self.cmd_profile, Command("profile"))
            self.dp.message.register(self.cmd_orders, Command("orders"))
            self.dp.message.register(self.cmd_support, Command("support"))
            self.dp.message.register(self.cmd_paysupport, Command("paysupport"))

            logger.info("Telegram bot initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to init Telegram bot: {e}")
            return False

    async def cmd_start(self, message: types.Message):
        webapp_url = settings.TELEGRAM_WEBAPP_URL or f"{settings.APP_URL}/telegram-app"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 OPEN VYRON", web_app=WebAppInfo(url=webapp_url))],
            [
                InlineKeyboardButton(text="🎮 Games", web_app=WebAppInfo(url=f"{webapp_url}?page=games")),
                InlineKeyboardButton(text="🛒 Marketplace", web_app=WebAppInfo(url=f"{webapp_url}?page=marketplace"))
            ],
            [
                InlineKeyboardButton(text="📦 Orders", web_app=WebAppInfo(url=f"{webapp_url}?page=orders")),
                InlineKeyboardButton(text="👤 Profile", web_app=WebAppInfo(url=f"{webapp_url}?page=profile"))
            ]
        ])

        text = (
            "Welcome to VYRON 🎮\n\n"
            "Your premium gaming commerce platform:\n"
            "• Game top-ups\n"
            "• Digital products\n"
            "• Marketplace\n"
            "• Donations\n\n"
            "Tap below to open VYRON!"
        )

        await message.answer(text, reply_markup=keyboard)

    async def cmd_help(self, message: types.Message):
        text = (
            "VYRON Help 🎮\n\n"
            "/start - Open VYRON Mini App\n"
            "/help - Show this help\n"
            "/profile - View your profile\n"
            "/orders - View your orders\n"
            "/support - Contact support\n"
            "/paysupport - Payment support\n\n"
            "Website: vyron.uz\n"
            "Support: @vyron_support"
        )
        await message.answer(text)

    async def cmd_profile(self, message: types.Message):
        webapp_url = settings.TELEGRAM_WEBAPP_URL or f"{settings.APP_URL}/telegram-app"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Open Profile", web_app=WebAppInfo(url=f"{webapp_url}?page=profile"))]
        ])
        await message.answer("View your profile in VYRON Mini App:", reply_markup=keyboard)

    async def cmd_orders(self, message: types.Message):
        webapp_url = settings.TELEGRAM_WEBAPP_URL or f"{settings.APP_URL}/telegram-app"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📦 My Orders", web_app=WebAppInfo(url=f"{webapp_url}?page=orders"))]
        ])
        await message.answer("Check your orders:", reply_markup=keyboard)

    async def cmd_support(self, message: types.Message):
        text = (
            "Support 🎧\n\n"
            "Need help? Contact us:\n"
            "• In-app support ticket\n"
            "• Telegram: @vyron_support\n"
            "• Email: support@vyron.uz\n\n"
            "We usually reply within 24 hours."
        )
        await message.answer(text)

    async def cmd_paysupport(self, message: types.Message):
        text = (
            "Payment Support 💳\n\n"
            "Having payment issues?\n"
            "• Check your payment provider\n"
            "• Verify transaction ID\n"
            "• Contact support with order number\n\n"
            "Supported: Payme, Click, Stripe"
        )
        await message.answer(text)

    async def send_notification(self, telegram_id: int, text: str, webapp_url: str = None):
        if not self.bot:
            logger.warning("Bot not initialized, cannot send notification")
            return False

        try:
            if webapp_url:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Open VYRON", web_app=WebAppInfo(url=webapp_url))]
                ])
                await self.bot.send_message(telegram_id, text, reply_markup=keyboard)
            else:
                await self.bot.send_message(telegram_id, text)
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram notification to {telegram_id}: {e}")
            return False

    async def send_order_notification(self, telegram_id: int, order_number: str, status: str, amount: float = None):
        status_emoji = {
            "CREATED": "📝",
            "PAID": "✅",
            "PROCESSING": "⚙️",
            "SUPPLIER_PROCESSING": "🔄",
            "COMPLETED": "🎉",
            "FAILED": "❌",
            "REFUNDED": "💸"
        }
        emoji = status_emoji.get(status, "📦")
        
        text = f"{emoji} Order {order_number}\nStatus: {status}"
        if amount:
            text += f"\nAmount: {amount} UZS"
        
        webapp_url = settings.TELEGRAM_WEBAPP_URL or f"{settings.APP_URL}/telegram-app"
        await self.send_notification(telegram_id, text, webapp_url)

    async def start_polling(self):
        if not self.bot or not self.dp:
            logger.warning("Bot not initialized, skipping polling")
            return

        self._running = True
        logger.info("Starting Telegram bot polling...")
        try:
            await self.dp.start_polling(self.bot)
        except asyncio.CancelledError:
            logger.info("Telegram bot polling cancelled")
        except Exception as e:
            logger.error(f"Telegram bot polling error: {e}")
        finally:
            self._running = False

    async def stop(self):
        self._running = False
        if self.bot:
            try:
                await self.bot.session.close()
            except:
                pass
        logger.info("Telegram bot stopped")

# Global instance
telegram_bot_service = TelegramBotService()

async def start_telegram_bot():
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("Telegram bot token not set, bot will not start")
        return
    
    initialized = await telegram_bot_service.init_bot()
    if initialized:
        await telegram_bot_service.start_polling()
