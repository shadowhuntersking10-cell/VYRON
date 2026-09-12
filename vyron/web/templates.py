"""Jinja2 environment + shared render context for SSR pages."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any, Dict

from fastapi import Request
from fastapi.templating import Jinja2Templates

from vyron.i18n import DEFAULT_LANGUAGE, LANGUAGE_LABELS, SUPPORTED_LANGUAGES, catalog, t
from vyron.security.sessions import get_session_user

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATE_DIR)

THEME_COOKIE = "vyron_theme"


def _money(value: Any, currency: str = "") -> str:
    try:
        from decimal import Decimal

        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return f"{value} {currency}".strip()
    return f"{amount} {currency}".strip()


def resolve_lang(request: Request) -> str:
    cookie_lang = request.cookies.get("vyron_lang")
    if cookie_lang in SUPPORTED_LANGUAGES:
        return cookie_lang
    accept = request.headers.get("accept-language", "")
    for part in accept.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED_LANGUAGES:
            return code
    return DEFAULT_LANGUAGE


def resolve_theme(request: Request, user) -> str:
    if user is not None and getattr(user, "theme", None) in {"light", "dark", "system"}:
        return user.theme
    cookie_theme = request.cookies.get(THEME_COOKIE)
    return cookie_theme if cookie_theme in {"light", "dark", "system"} else "system"


templates.env.globals.update(
    {
        "site_name": "VYRON",
        "tagline": "PLAY. BUY. DONATE.",
        "current_year": datetime.now(UTC).year,
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "language_labels": LANGUAGE_LABELS,
    }
)
templates.env.filters["money"] = _money


def render(request: Request, name: str, user=None, status_code: int = 200, **context: Any):
    """Render with the standard context: user, lang, t(), theme, i18n bundle, csrf."""
    from vyron.db.base import get_session_factory
    from vyron.security.csrf import CSRF_COOKIE, issue_csrf_cookie

    if user is None:
        db = get_session_factory()()
        try:
            user = get_session_user(db, request)
        finally:
            db.close()

    lang = resolve_lang(request)
    csrf_token = request.cookies.get(CSRF_COOKIE, "")

    ctx: Dict[str, Any] = {
        "request": request,
        "user": user,
        "lang": lang,
        "t": lambda key, **params: t(key, lang, **params),
        "theme": resolve_theme(request, user),
        "i18n_bundle": json.dumps(catalog(lang), ensure_ascii=False),
        "csrf_token": csrf_token,
        "public_base_url": "",
    }
    ctx.update(context)
    response = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if not csrf_token:
        issue_csrf_cookie(response)
    return response
