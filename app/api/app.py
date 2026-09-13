"""FastAPI application factory: routes, templates, static, error pages."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.utils.i18n import get_translator, normalize_lang

log = logging.getLogger("vyron.app")
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class LangMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        lang = request.cookies.get("vyron_lang") or request.headers.get("accept-language", "")[:2]
        request.state.lang = normalize_lang(lang)
        response = await call_next(request)
        return response


def template_context(request: Request, **extra) -> dict:
    lang = getattr(request.state, "lang", "uz")
    return {
        "request": request,
        "lang": lang,
        "t": get_translator(lang),
        "settings": settings,
        "is_admin": False,
        **extra,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="VYRON", version="1.0.0", docs_url="/api/docs", redoc_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LangMiddleware)

    # Static + uploads
    static_dir = BASE_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    uploads_dir = Path(settings.STORAGE_LOCAL_DIR)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    # ---- page routes (HTML) ----
    from app.api import pages  # noqa: PLC0415

    app.include_router(pages.router)

    # ---- JSON API ----
    from app.api import (  # noqa: PLC0415
        admin_router, auth, checkout, donations, favorites, games, health,
        locale, marketplace, media, miniapp_api, notifications, orders,
        payments, products, reviews, search, sellers, support, telegram_api,
        user, wallet, webhooks,
    )

    app.include_router(health.router)
    app.include_router(locale.router)
    app.include_router(auth.router)
    app.include_router(telegram_api.router)
    app.include_router(games.router)
    app.include_router(products.router)
    app.include_router(checkout.router)
    app.include_router(orders.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    app.include_router(marketplace.router)
    app.include_router(sellers.router)
    app.include_router(donations.router)
    app.include_router(support.router)
    app.include_router(notifications.router)
    app.include_router(search.router)
    app.include_router(favorites.router)
    app.include_router(reviews.router)
    app.include_router(wallet.router)
    app.include_router(user.router)
    app.include_router(media.router)
    app.include_router(miniapp_api.router)
    app.include_router(admin_router.router)

    # ---- error pages (never leak stack traces) ----
    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        return templates.TemplateResponse(request, "errors/404.html", template_context(request), status_code=404
        )

    @app.exception_handler(403)
    async def forbidden(request: Request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return templates.TemplateResponse(request, "errors/403.html", template_context(request), status_code=403
        )

    @app.exception_handler(500)
    async def server_error(request: Request, exc):
        log.exception("unhandled error: %s", exc)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "internal_error"}, status_code=500)
        return templates.TemplateResponse(request, "errors/500.html", template_context(request), status_code=500
        )

    return app
