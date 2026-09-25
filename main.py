#!/usr/bin/env python3
"""VYRON — single entrypoint.

    python main.py

Starts EVERYTHING in one process:
  * database migrations + seed
  * website + webapp (FastAPI + static frontend)
  * REST API
  * Telegram bot (WebApp button on /start)
  * automatic fulfillment worker (Payerpin)
  * scheduled catalog sync

Configuration comes from environment / .env (see .env.example).
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import get_settings  # noqa: E402
from app.logging_config import configure_logging, get_logger  # noqa: E402

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("vyron.main")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app.api import account, admin, auth, cart, catalog, checkout, sandbox, support, webhooks  # noqa: E402
from app import db as db_module  # noqa: E402
from app.db import BASE_SQLITE_PATH, get_engine, init_engine  # noqa: E402
from app.migrations import run_migrations, seed_database  # noqa: E402

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Boot migrations, worker, bot and schedulers inside the server loop."""
    Path(BASE_SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    init_engine()
    run_migrations()
    seed_database()
    log.info("VYRON database ready (dialect=%s)", db_module.db_dialect)

    from app.services.fulfillment import FulfillmentWorker, run_catalog_scheduler
    from bot.bot import run_bot

    worker = FulfillmentWorker()
    tasks = [
        asyncio.create_task(worker.run(), name="fulfillment-worker"),
        asyncio.create_task(run_bot(), name="telegram-bot"),
        asyncio.create_task(run_catalog_scheduler(), name="catalog-scheduler"),
    ]
    log.info(
        "VYRON started — web=%s:%s | payment=%s | payerpin=%s | telegram=%s",
        settings.host,
        settings.port,
        settings.payment_provider or "NOT CONFIGURED",
        "configured" if settings.payerpin_configured() else "NOT CONFIGURED",
        "configured" if settings.telegram_configured() else "NOT CONFIGURED",
    )
    try:
        yield
    finally:
        worker.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log.info("VYRON shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="VYRON API",
        version="1.0.0",
        docs_url="/api/docs" if settings.app_debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Telegram WebApp + browser; cookies are SameSite=Lax
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline' https://telegram.org; "
            "connect-src 'self' https: wss:; frame-ancestors 'self' https://web.telegram.org",
        )
        if not settings.app_debug:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception):
        log.error("unhandled error on %s: %s", request.url.path, type(exc).__name__)
        detail = "internal_error"
        if settings.app_debug:
            detail = f"{type(exc).__name__}: {exc}"[:500]
        return JSONResponse(status_code=500, content={"detail": detail})

    # API routers
    app.include_router(auth.router)
    app.include_router(catalog.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    app.include_router(account.router)
    app.include_router(webhooks.router)
    app.include_router(support.router)
    app.include_router(admin.router)
    app.include_router(sandbox.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {
            "status": "ok",
            "service": "VYRON",
            "database": db_module.db_dialect,
            "payment_configured": settings.payment_configured(),
            "payerpin_configured": settings.payerpin_configured(),
            "telegram_configured": settings.telegram_configured(),
        }

    # static frontend (website + Telegram webapp)
    if WEB_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("assets/"):
                return JSONResponse(status_code=404, content={"detail": "not_found"})
            index = WEB_DIR / "index.html"
            return FileResponse(str(index))

    return app


app = create_app()


def main() -> None:
    import uvicorn

    log.info("Starting VYRON on %s:%s ...", settings.host, settings.port)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
