"""VYRON - single entry point.

Starts EVERYTHING with one command:

    python main.py

Orchestrates:
  - configuration load + validation
  - database init + table check (+ seed)
  - Redis check (optional)
  - FastAPI (uvicorn, in-process)
  - Telegram bot (aiogram polling)
  - background workers + scheduled tasks

Graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vyron.main")


def validate_config() -> list[str]:
    warnings: list[str] = []
    if len(settings.APP_SECRET) < 32:
        warnings.append("APP_SECRET is shorter than 32 chars - set a strong secret in production!")
    if not settings.telegram_configured:
        warnings.append("TELEGRAM_BOT_TOKEN missing - bot disabled (web + Mini App still work).")
    if not settings.using_mysql:
        warnings.append("MySQL not configured - using local SQLite dev fallback (vyron_dev.db).")
    if not settings.REDIS_URL:
        warnings.append("REDIS_URL missing - using in-process rate limiting (set Redis in production).")
    if not (settings.payme_configured or settings.click_configured or settings.stripe_configured):
        warnings.append("No payment provider configured - checkout will show 'not configured'.")
    if not settings.supplier_configured:
        warnings.append("No supplier API configured - top-up orders route to MANUAL_REVIEW.")
    if not settings.smtp_configured:
        warnings.append("SMTP not configured - password-reset emails will be logged, not sent.")
    return warnings


async def init_database() -> None:
    from app.database import check_connection, create_all_tables, get_engine  # noqa: PLC0415

    get_engine()
    ok, detail = await check_connection()
    if not ok:
        # VYRON requires MySQL. A local SQLite fallback is allowed ONLY for
        # development when no MySQL credentials were configured at all.
        # Production, or explicit-but-unreachable MySQL, fails fast.
        mysql_explicit = settings.using_mysql
        if settings.is_production or mysql_explicit:
            raise RuntimeError(
                f"Database unreachable in {settings.APP_ENV} mode: {detail}. "
                "VYRON requires MySQL - check MYSQL_HOST/PORT/DATABASE/USER/PASSWORD."
            )
        log.error("Database unreachable (%s).", detail)
        raise RuntimeError(f"Database unreachable: {detail}")
    await create_all_tables()

    from app.database import ensure_schema  # noqa: PLC0415

    await ensure_schema()

    from app.database import get_session_factory  # noqa: PLC0415
    from app.seed import seed_all  # noqa: PLC0415

    factory = get_session_factory()
    async with factory() as db:
        await seed_all(db)
    log.info("Database ready (mysql=%s)", settings.using_mysql)


async def init_redis() -> None:
    if not settings.REDIS_URL:
        return
    try:
        import redis.asyncio as aioredis  # noqa: PLC0415

        client = aioredis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        log.info("Redis connected")
    except Exception as exc:
        log.warning("Redis unreachable (%s) - continuing without it", exc)


async def amain() -> None:
    from app.api.app import create_app  # noqa: PLC0415
    from app import scheduler  # noqa: PLC0415
    from app.telegram.bot import get_bot_service  # noqa: PLC0415

    log.info("=== VYRON starting (env=%s) ===", settings.APP_ENV)
    for w in validate_config():
        log.warning("CONFIG: %s", w)

    await init_database()
    await init_redis()

    app = create_app()
    config = uvicorn.Config(
        app, host=settings.APP_HOST, port=settings.APP_PORT,
        log_level="warning", access_log=False,
    )
    server = uvicorn.Server(config)

    bot = get_bot_service()
    await bot.start()
    workers = scheduler.start_workers()

    stop_event = asyncio.Event()

    def _shutdown(*_args) -> None:
        log.info("Shutdown signal received...")
        stop_event.set()
        server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    log.info("VYRON up at http://%s:%s  (Mini App: /miniapp, Admin: /admin)", settings.APP_HOST, settings.APP_PORT)
    await server.serve()

    # ---- graceful shutdown ----
    await scheduler.stop_workers(workers)
    await bot.stop()
    from app.database import dispose_engine  # noqa: PLC0415

    await dispose_engine()
    log.info("VYRON stopped cleanly.")


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        log.info("Interrupted.")


if __name__ == "__main__":
    main()
