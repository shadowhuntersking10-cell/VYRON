"""FastAPI application factory: website + API + mini-app backend + webhooks."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import models  # noqa: F401 - register models
from app.api import api_router
from app.auth.service import AuthService
from app.config import settings
from app.database import SessionLocal
from app.utils.i18n import normalize_lang, t
from app.utils.logging import get_logger
from app.web.routes import router as web_router

log = get_logger("vyron.app")
ROOT = Path(__file__).resolve().parent.parent


def money(value) -> str:
    try:
        return f"{float(value or 0):,.0f}"
    except Exception:
        return "0"


def create_app() -> FastAPI:
    app = FastAPI(title="VYRON", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")

    # static + templates
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
    templates = Jinja2Templates(directory=str(ROOT / "templates"))
    templates.env.globals["t"] = t
    templates.env.globals["money"] = money
    templates.env.globals["normalize_lang"] = normalize_lang
    app.state.templates = templates

    @app.middleware("http")
    async def session_middleware(request: Request, call_next):
        # language
        lang = normalize_lang(request.query_params.get("lang") or request.cookies.get("vyron_lang"))
        request.state.lang = lang
        # session -> user
        token = request.cookies.get(settings.SESSION_COOKIE, "")
        # also allow Telegram Mini App header auth token
        if not token:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:]
        request.state.user = None
        request.state.session = None
        if token:
            db = SessionLocal()
            try:
                user, sess = AuthService(db).get_session_user(token)
                if user:
                    # re-fetch per-request in route handlers; keep detached-safe copy of attrs
                    request.state.user = user
                    request.state.session = sess
                    # keep objects usable after session close
                    db.expunge_all()
                else:
                    db.close()
                    db = None
            except Exception:
                pass
            finally:
                try:
                    if db is not None:
                        db.close()
                except Exception:
                    pass
        # CSRF check for cookie-based mutating web form posts (non-API JSON uses same-origin + csrf header)
        response = await call_next(request)
        # security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.query_params.get("lang"):
            response.set_cookie("vyron_lang", lang, max_age=365 * 86400, path="/", samesite="lax")
        return response

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "not_found"}, status_code=404)
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "user": getattr(request.state, "user", None),
             "lang": getattr(request.state, "lang", "uz"), "theme": "dark",
             "is_admin": False, "is_seller": False, "settings": settings,
             "code": 404, "seo": {"title": "Not found — VYRON"}},
            status_code=404,
        )

    app.include_router(api_router)
    app.include_router(web_router)
    log.info("VYRON app created (env=%s)", settings.APP_ENV)
    return app
