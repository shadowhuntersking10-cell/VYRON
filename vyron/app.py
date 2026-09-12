"""FastAPI application factory — one shared backend for the website,
Telegram Mini App, bot and admin panel.

Wiring order matters: CORS → security headers → CSRF → routes.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from vyron.config import settings
from vyron.errors import install_error_handlers
from vyron.logging import get_logger, setup_logging
from vyron.security.csrf import CsrfMiddleware
from vyron.security.headers import SecurityHeadersMiddleware

log = get_logger("vyron.app")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="VYRON API",
        description="VYRON — gaming & digital marketplace backend (website, Telegram Mini App, bot, admin).",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Requested-With", "Accept-Language"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CsrfMiddleware)

    install_error_handlers(app)

    # --- API routers ------------------------------------------------------------------
    from vyron.api import (
        admin,
        auth,
        cart,
        checkout,
        donations,
        games,
        health,
        i18n,
        marketplace,
        notifications,
        orders,
        search,
        seller,
        support,
        telegram,
        uploads,
        users,
        webhooks,
    )

    for module in (
        health, auth, users, games, cart, checkout, orders, webhooks, donations, marketplace,
        seller, telegram, support, search, notifications, uploads, i18n, admin,
    ):
        app.include_router(module.router)

    # --- Web (SSR) ---------------------------------------------------------------------
    from vyron.web.router import router as web_router

    app.include_router(web_router)

    # --- Static assets -------------------------------------------------------------------
    os.makedirs(STATIC_DIR, exist_ok=True)
    os.makedirs(settings.local_upload_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    log.info("application created", env=settings.vyron_env, docs="/api/docs")
    return app
