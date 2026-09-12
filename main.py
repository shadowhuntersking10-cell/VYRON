#!/usr/bin/env python3
"""VYRON — single entry point.

`python main.py` starts EVERYTHING:
  1. preflight checks   — MySQL + Redis must be reachable (clear error otherwise)
  2. database migrations — alembic upgrade head (AUTO_MIGRATE_ON_START=1)
  3. seed               — super admin + default settings (+ demo catalog in dev)
  4. background workers — Redis Streams queue consumers + periodic scheduler
  5. telegram bot       — long polling (only when TELEGRAM_BOT_TOKEN is set)
  6. web server         — uvicorn serving the FastAPI app (API + SSR website + Mini App)

Graceful shutdown on SIGINT/SIGTERM: server stops accepting, workers and bot shut
down, then the process exits.
"""

from __future__ import annotations

import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

BANNER = r"""
 __      _______ _____  ____  _   _
 \ \    / /_   _|  __ \|  _ \| \ | |
  \ \  / /  | | | |__) | |_) |  \| |
   \ \/ /   | | |  _  /|  _ <| |\  |
    \_/_/   |_| |_| \_\|_| \_\_| \_|
   PLAY. BUY. DONATE.
"""


def preflight() -> None:
    """Fail fast with a clear message when MySQL or Redis are unreachable."""
    from vyron.config import settings
    from vyron.logging import get_logger

    log = get_logger("vyron.main")

    from sqlalchemy import text

    from vyron.db.base import get_engine

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        log.info("MySQL connection OK", database=settings.database_url.split("@")[-1])
    except Exception as exc:
        print("\n[STARTUP ERROR] MySQL is not reachable.\n"
              f"  DATABASE_URL={settings.database_url.split('@')[-1]}\n"
              f"  Reason: {exc}\n"
              "  Start MySQL and verify DATABASE_URL in .env, then re-run `python main.py`.\n",
              file=sys.stderr)
        raise SystemExit(2)

    try:
        from vyron.redis_client import redis_ping

        if not redis_ping():
            raise RuntimeError("PING failed")
        log.info("Redis connection OK", redis=settings.redis_url)
    except Exception as exc:
        print("\n[STARTUP ERROR] Redis is not reachable.\n"
              f"  REDIS_URL={settings.redis_url}\n"
              f"  Reason: {exc}\n"
              "  Start Redis and verify REDIS_URL in .env, then re-run `python main.py`.\n",
              file=sys.stderr)
        raise SystemExit(2)


def migrate() -> None:
    from vyron.config import settings
    from vyron.logging import get_logger

    log = get_logger("vyron.main")
    if not settings.auto_migrate_on_start:
        log.info("AUTO_MIGRATE_ON_START=0 — skipping migrations")
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(BASE_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BASE_DIR, "migrations"))
    command.upgrade(cfg, "head")
    # alembic's fileConfig replaces root handlers — restore ours so seed/worker
    # startup logs stay visible in VYRON's own format
    from vyron.logging import setup_logging

    setup_logging(level=settings.log_level, as_json=settings.log_json, force=True)
    log.info("database migrations applied")


def seed() -> None:
    from vyron.db.base import get_session_factory
    from vyron.seed import run_seed

    db = get_session_factory()()
    try:
        run_seed(db)
    finally:
        db.close()


async def serve(app) -> None:
    import uvicorn

    from vyron.config import settings

    config = uvicorn.Config(
        app,
        host=settings.vyron_host,
        port=settings.vyron_port,
        log_level="info",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config)
    # uvicorn installs its own SIGINT/SIGTERM handlers inside serve() and sets
    # should_exit — asyncio.run then unwinds and main() stops workers/bot.
    await server.serve()


def main() -> None:
    print(BANNER)
    from vyron.config import settings
    from vyron.logging import get_logger, setup_logging

    setup_logging(level=settings.log_level, as_json=settings.log_json)
    log = get_logger("vyron.main")

    preflight()
    migrate()
    seed()

    from vyron.app import create_app
    from vyron.workers import start_workers

    app = create_app()
    workers = start_workers()

    bot = None
    if settings.telegram_configured:
        try:
            from vyron.telegram_bot import BotRunner

            bot = BotRunner()
            bot.start()
            log.info("telegram bot started")
        except Exception as exc:
            log.error(f"telegram bot failed to start (web app continues): {exc}")
            bot = None
    else:
        log.warning("TELEGRAM_BOT_TOKEN not set — telegram bot disabled (everything else runs)")

    log.info("VYRON starting", host=settings.vyron_host, port=settings.vyron_port, env=settings.vyron_env)
    log.info("website", url=f"http://localhost:{settings.vyron_port}/")
    log.info("miniapp", url=f"http://localhost:{settings.vyron_port}/miniapp")
    log.info("api docs", url=f"http://localhost:{settings.vyron_port}/api/docs")

    try:
        asyncio.run(serve(app))
    except KeyboardInterrupt:
        pass
    finally:
        log.info("shutting down…")
        if bot is not None:
            bot.stop()
        workers.stop()
        log.info("VYRON stopped cleanly")


if __name__ == "__main__":
    main()
