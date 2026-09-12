"""Structured error system.

Every API error is rendered as:
    {"success": false, "error": {"code": "...", "message": "..."}}

Stack traces are never returned to clients (logged server-side only).
Error codes are stable, machine-readable and translatable on the frontend.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from vyron.logging import get_logger

log = get_logger("vyron.errors")


class VyronError(Exception):
    """Base class for all structured VYRON errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message or self.default_message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"success": False, "error": {"code": self.code, "message": self.message}}
        if self.details:
            payload["error"]["details"] = self.details
        return payload


# --- Configuration / integration -------------------------------------------------
class NotConfiguredError(VyronError):
    code = "NOT_CONFIGURED"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = "This integration is not configured on the server."


class ProviderNotConfiguredError(NotConfiguredError):
    code = "PAYMENT_PROVIDER_NOT_CONFIGURED"
    default_message = "Payment provider is not configured."


class SupplierNotConfiguredError(NotConfiguredError):
    code = "SUPPLIER_NOT_CONFIGURED"
    default_message = "Supplier integration is not configured."


class SmtpNotConfiguredError(NotConfiguredError):
    code = "SMTP_NOT_CONFIGURED"
    default_message = "Email delivery is not configured."


class TelegramNotConfiguredError(NotConfiguredError):
    code = "TELEGRAM_NOT_CONFIGURED"
    default_message = "Telegram integration is not configured."


# --- Auth / access ---------------------------------------------------------------
class AuthError(VyronError):
    code = "AUTH_ERROR"
    http_status = status.HTTP_401_UNAUTHORIZED
    default_message = "Authentication required."


class InvalidCredentialsError(AuthError):
    code = "INVALID_CREDENTIALS"
    default_message = "Invalid email or password."


class EmailNotVerifiedError(AuthError):
    code = "EMAIL_NOT_VERIFIED"
    default_message = "Please verify your email address first."


class AccountDisabledError(AuthError):
    code = "ACCOUNT_DISABLED"
    http_status = status.HTTP_403_FORBIDDEN
    default_message = "This account has been disabled."


class ForbiddenError(VyronError):
    code = "FORBIDDEN"
    http_status = status.HTTP_403_FORBIDDEN
    default_message = "You do not have permission to perform this action."


class RateLimitedError(VyronError):
    code = "RATE_LIMITED"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = "Too many attempts. Please try again later."


class CsrfError(VyronError):
    code = "CSRF_FAILED"
    http_status = status.HTTP_403_FORBIDDEN
    default_message = "CSRF validation failed. Please refresh the page."


# --- Validation / resources ----------------------------------------------------------
class ValidationError(VyronError):
    code = "VALIDATION_ERROR"
    http_status = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    default_message = "Validation failed."


class NotFoundError(VyronError):
    code = "NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND
    default_message = "Resource not found."


class ConflictError(VyronError):
    code = "CONFLICT"
    http_status = status.HTTP_409_CONFLICT
    default_message = "Resource conflict."


# --- Commerce -------------------------------------------------------------------------
class OrderStateError(VyronError):
    code = "INVALID_ORDER_TRANSITION"
    http_status = status.HTTP_409_CONFLICT
    default_message = "This order status transition is not allowed."


class PaymentError(VyronError):
    code = "PAYMENT_FAILED"
    http_status = status.HTTP_402_PAYMENT_REQUIRED
    default_message = "Payment could not be completed."


class PaymentVerificationError(PaymentError):
    code = "PAYMENT_VERIFICATION_FAILED"
    default_message = "Payment could not be verified."


class WebhookVerificationError(VyronError):
    code = "WEBHOOK_SIGNATURE_INVALID"
    http_status = status.HTTP_400_BAD_REQUEST
    default_message = "Webhook signature verification failed."


class CouponError(VyronError):
    code = "COUPON_INVALID"
    http_status = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    default_message = "Coupon is not valid for this order."


class InsufficientBalanceError(VyronError):
    code = "INSUFFICIENT_BALANCE"
    http_status = status.HTTP_409_CONFLICT
    default_message = "Insufficient balance."


class FraudReviewError(VyronError):
    code = "ORDER_UNDER_REVIEW"
    http_status = status.HTTP_409_CONFLICT
    default_message = "This order requires manual review."



def _render_error_page(request: Request, status_code: int, code: str, message: str):
    """Render the SSR error page for browser requests; None if the client wants JSON."""
    accept = request.headers.get("accept", "")
    if request.url.path.startswith("/api/") or "text/html" not in accept:
        return None
    try:
        from vyron.web.templates import render

        heading_key = {
            400: "errors.VALIDATION_ERROR", 401: "errors.AUTH_ERROR", 403: "errors.FORBIDDEN",
            404: "errors.NOT_FOUND", 409: "errors.CONFLICT", 422: "errors.VALIDATION_ERROR",
            429: "errors.RATE_LIMITED",
        }.get(status_code, "errors.INTERNAL_ERROR")
        return render(
            request,
            "error.html",
            status=status_code,
            code=code,
            message=message,
            heading=_lazy_t(heading_key, request),
            status_code=status_code,
        )
    except Exception:
        return None


def _lazy_t(key: str, request: Request) -> str:
    try:
        from vyron.i18n import normalize_lang, t

        lang = normalize_lang(request.cookies.get("vyron_lang", ""))
        return t(key, lang)
    except Exception:
        return key


def error_response(err: VyronError) -> JSONResponse:
    return JSONResponse(status_code=err.http_status, content=err.to_payload())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(VyronError)
    async def _vyron_error_handler(request: Request, exc: VyronError) -> JSONResponse:
        if exc.http_status >= 500:
            log.error(str(exc), path=request.url.path, code=exc.code)
        else:
            log.warning(str(exc), path=request.url.path, code=exc.code)
        page = _render_error_page(request, exc.http_status, exc.code, str(exc))
        if page is not None:
            return page
        return error_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            409: "CONFLICT",
            429: "RATE_LIMITED",
        }
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "error": {"code": code_map.get(exc.status_code, "HTTP_ERROR"), "message": str(exc.detail)},
                },
            )
        page = _render_error_page(request, exc.status_code, code_map.get(exc.status_code, "HTTP_ERROR"), str(exc.detail))
        if page is not None:
            return page
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = []
        for err in exc.errors()[:20]:
            details.append({"field": ".".join(str(loc) for loc in err.get("loc", [])), "issue": err.get("msg", "")})
        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content={
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "Validation failed.", "details": details},
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception(f"Unhandled error on {request.url.path}: {exc}")
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )
