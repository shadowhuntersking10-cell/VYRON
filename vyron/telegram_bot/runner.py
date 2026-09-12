"""BotRunner — runs the python-telegram-bot Application (long polling) inside a
dedicated daemon thread with its own asyncio loop, so `python main.py` can start
and gracefully stop it alongside the web server and workers."""

from __future__ import annotations

import asyncio
import threading
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from vyron.config import settings
from vyron.errors import TelegramNotConfiguredError
from vyron.logging import get_logger

log = get_logger("vyron.telegram_bot.runner")


class BotRunner:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._app: Optional[Application] = None
        self._started = threading.Event()
        self.error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._started.is_set()

    def start(self) -> None:
        if not settings.telegram_configured:
            raise TelegramNotConfiguredError(
                "Telegram bot requested but TELEGRAM_BOT_TOKEN is not configured."
            )
        self._thread = threading.Thread(target=self._run, name="telegram-bot", daemon=True)
        self._thread.start()
        if not self._started.wait(timeout=20):
            raise RuntimeError(f"Telegram bot failed to start: {self.error or 'timeout'}")

    def _build_application(self) -> Application:
        from vyron.telegram_bot import handlers

        app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .post_init(handlers.post_init)
            .build()
        )
        app.add_handler(CommandHandler("start", handlers.cmd_start))
        app.add_handler(CommandHandler("help", handlers.cmd_help))
        app.add_handler(CommandHandler("orders", handlers.cmd_orders))
        app.add_handler(CommandHandler("profile", handlers.cmd_profile))
        app.add_handler(CommandHandler("support", handlers.cmd_support))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_unknown))
        return app

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            app = self._build_application()
            self._app = app
            loop.run_until_complete(app.initialize())
            loop.run_until_complete(app.start())
            loop.run_until_complete(app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True))
            self._started.set()
            log.info("telegram bot polling started")
            loop.run_forever()
        except Exception as exc:
            self.error = str(exc)
            log.error("telegram bot crashed", error=str(exc))
            self._started.set()  # unblock start() so main.py reports the failure
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()

    def stop(self) -> None:
        loop, app = self._loop, self._app
        if loop is None:
            return

        async def _shutdown() -> None:
            try:
                if app is not None:
                    if app.updater and app.updater.running:
                        await app.updater.stop()
                    if app.running:
                        await app.stop()
                    await app.shutdown()
            except Exception as exc:
                log.warning("bot shutdown error", error=str(exc))

        try:
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_shutdown(), loop)
                future.result(timeout=10)
                loop.call_soon_threadsafe(loop.stop)
        except Exception as exc:
            log.warning("bot stop error", error=str(exc))
        if self._thread is not None:
            self._thread.join(timeout=10)
        log.info("telegram bot stopped")
