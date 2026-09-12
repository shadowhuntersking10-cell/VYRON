"""CSRF protection: double-submit cookie pattern.

A non-HttpOnly `vyron_csrf` cookie carries a random token; mutating API
requests must echo it in the `X-CSRF-Token` header. Combined with SameSite=Lax
session cookies this blocks cross-site forged requests.

Exempt: signed webhooks (their own signature verification), Telegram
initData auth (cryptographically authenticated), health endpoints.
"""

from __future__ import annotations

import secrets

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from vyron.config import settings
from vyron.security.hashing import constant_time_equals

CSRF_COOKIE = "vyron_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
EXEMPT_PREFIXES = (
    "/api/webhooks/",
    "/api/telegram/auth",
    "/api/telegram/miniapp",
    "/health",
    "/ready",
    "/miniapp",  # Telegram WebView pages authenticate via initData
)


def issue_csrf_cookie(response: Response) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=86400 * 30,
        httponly=False,  # JS must read it to send the header
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )
    return token


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not settings.csrf_enabled:
            return response

        path = request.url.path
        exempt = any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)

        if request.method in SAFE_METHODS:
            if not exempt and path.startswith("/api/") and CSRF_COOKIE not in request.cookies:
                issue_csrf_cookie(response)
            return response

        if exempt or not path.startswith("/api/"):
            return response

        cookie_token = request.cookies.get(CSRF_COOKIE, "")
        header_token = request.headers.get(CSRF_HEADER, "")
        if not cookie_token or not header_token or not constant_time_equals(cookie_token, header_token):

            return Response(
                status_code=403,
                media_type="application/json",
                content='{"success": false, "error": {"code": "CSRF_FAILED", "message": "CSRF validation failed. Please refresh the page."}}',
            )
        return response
