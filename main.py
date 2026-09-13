#!/usr/bin/env python3
"""VYRON - single entrypoint. `python main.py` starts everything:

1. FastAPI backend + public website + Mini App backend + webhooks
2. Telegram Bot (aiogram, polling)
3. Background workers / scheduled jobs

Graceful shutdown on SIGINT/SIGTERM.
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys


def preflight() -> int:
    """Verify configuration + DB connectivity. Returns exit code (0 ok)."""
    from app.config import settings
    from app.database import check_connectivity
    from app.utils.logging import get_logger
    log = get_logger("vyron.main")

    print("=" * 60)
    print(f"VYRON starting (env={settings.APP_ENV})")
    print("=" * 60)

    url, is_mysql = settings.effective_database_url()
    if not is_mysql:
        if settings.is_production:
            print("FATAL: Production requires MySQL. Set DATABASE_URL or MYSQL_* variables.")
            print("See README.md (MySQL setup) and .env.example.")
            return 2
        print("WARNING: MySQL not configured - using local dev.db (SQLite) for DEVELOPMENT ONLY.")
        print("         Set MYSQL_* / DATABASE_URL for production. See README.md.")
    else:
        safe = url.split("@")[-1] if "@" in url else "mysql"
        print(f"Database: MySQL ({safe})")

    ok, msg = check_connectivity()
    print(msg)
    if not ok:
        print("FATAL: cannot connect to database. Check MYSQL_*/DATABASE_URL and that MySQL is running.")
        return 3

    # provider statuses (honest, non-fake)
    print("--- integration status ---")
    print(f"Telegram bot: {'CONFIGURED' if settings.TELEGRAM_BOT_TOKEN else 'NOT CONFIGURED'}")
    print(f"Payme:  {'CONFIGURED' if settings.PAYME_MERCHANT_ID and settings.PAYME_SECRET else 'NOT CONFIGURED'}")
    print(f"Click:  {'CONFIGURED' if settings.CLICK_MERCHANT_ID and settings.CLICK_SECRET else 'NOT CONFIGURED'}")
    print(f"Stripe: {'CONFIGURED' if settings.STRIPE_SECRET_KEY else 'NOT CONFIGURED'}")
    print(f"Supplier API: {'CONFIGURED' if settings.SUPPLIER_API_URL and settings.SUPPLIER_API_KEY else 'NOT CONFIGURED (orders -> MANUAL_REVIEW)'}")
    print(f"SALES_ENABLED={settings.SALES_ENABLED} PAYMENTS_ENABLED={settings.PAYMENTS_ENABLED} "
          f"SUPPLIER_ORDERS_ENABLED={settings.SUPPLIER_ORDERS_ENABLED} LOSS_SELLING={settings.LOSS_SELLING}")
    print(f"Admin Telegram IDs: {sorted(settings.admin_telegram_ids) or '(none)'}")
    print("=" * 60)
    return 0


def init_and_seed() -> None:
    from app.database import SessionLocal, init_db
    from app.seed import seed
    from app import models
    init_db()
    db = SessionLocal()
    try:
        games = db.query(models.Game).count()
        if games == 0:
            print("Seeding initial catalog...")
            seed(db)
        else:
            # ensure new seed items exist (idempotent)
            seed(db)
    finally:
        db.close()


async def serve(stop: asyncio.Event, host: str, port: int) -> None:
    import uvicorn
    from app.app import create_app
    config = uvicorn.Config(create_app(), host=host, port=port, log_level="info")
    server = uvicorn.Server(config)

    async def _watch():
        await stop.wait()
        server.should_exit = True

    watcher = asyncio.create_task(_watch())
    await server.serve()
    watcher.cancel()


async def amain(args) -> int:
    from app.telegram.bot import run_bot
    from app.worker import run_workers
    from app.config import settings
    from app.utils.logging import get_logger
    log = get_logger("vyron.main")

    code = preflight()
    if code != 0:
        return code
    init_and_seed()

    stop = asyncio.Event()

    def _signal(*_a):
        print("\nShutdown requested...")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: stop.set())

    host = args.host or settings.HOST
    port = args.port or settings.PORT
    log.info("VYRON serving on http://%s:%s", host, port)
    await asyncio.gather(
        serve(stop, host, port),
        run_bot(stop),
        run_workers(stop),
    )
    log.info("VYRON stopped cleanly.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="VYRON - run the whole platform")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--check", action="store_true", help="run preflight checks only")
    parser.add_argument("--seed-only", action="store_true", help="init db + seed, then exit")
    args = parser.parse_args()

    if args.check:
        sys.exit(preflight())
    if args.seed_only:
        code = preflight()
        if code != 0:
            sys.exit(code)
        init_and_seed()
        print("DB initialized + seeded.")
        return
    try:
        code = asyncio.run(amain(args))
    except KeyboardInterrupt:
        code = 0
    sys.exit(code)


if __name__ == "__main__":
    main()
