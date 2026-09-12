"""Structured JSON logging for VYRON.

Rules enforced here:
- one logger factory used by every subsystem (api, workers, bot, services)
- secrets are never logged (a redaction filter scrubs known key patterns)
- production never emits stack traces to clients (handled in errors.py); logs keep them.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any, MutableMapping

_REDACT_PATTERNS = [
    re.compile(r"(?i)(secret|token|password|passwd|api[_-]?key|authorization|signature)(\"?[=:]\s*\"?)([^\s\",;}]+)"),
]

_SENSITIVE_KEYS = {
    "password", "passwd", "secret", "token", "api_key", "apikey", "authorization",
    "session_secret", "bot_token", "stripe_secret_key", "payme_secret", "click_secret",
    "supplier_api_key", "supplier_api_secret", "s3_secret_key", "smtp_password",
    "password_hash", "new_password", "confirm_password", "access_token", "refresh_token",
}


def _redact(value: str) -> str:
    for pattern in _REDACT_PATTERNS:
        value = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}***REDACTED***", value)
    return value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            record.args = tuple(
                _redact(a) if isinstance(a, str) else a for a in record.args  # type: ignore[assignment]
            ) if isinstance(record.args, tuple) else record.args
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: MutableMapping[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload["context"] = {
                k: ("***REDACTED***" if k.lower() in _SENSITIVE_KEYS else v) for k, v in extra.items()
            }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{time.strftime('%H:%M:%S')} {record.levelname:<7} {record.name}: {_redact(record.getMessage())}"
        context = getattr(record, "context", None)
        if isinstance(context, dict) and context:
            rendered = " ".join(
                f"{k}={'***REDACTED***' if k.lower() in _SENSITIVE_KEYS else v}" for k, v in context.items()
            )
            base += f" | {rendered}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_RESERVED_KWARGS = {"exc_info", "stack_info", "stacklevel", "extra"}


class ContextLoggerAdapter(logging.LoggerAdapter):
    """Structured logger: arbitrary call kwargs become JSON context fields.

    log.info("order paid", number=order.number) -> {"message": "order paid",
    "context": {"number": ...}}. Logger-bound context from get_logger(name, **ctx)
    is merged in (call kwargs win).
    """

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]):
        context = {**(self.extra or {})}
        for key in list(kwargs.keys()):
            if key not in _RESERVED_KWARGS:
                context[key] = kwargs.pop(key)
        extra = kwargs.setdefault("extra", {})
        extra["context"] = context
        return msg, kwargs


_configured = False


def setup_logging(level: str = "INFO", as_json: bool = True, force: bool = False) -> None:
    """Configure root logging. force=True re-applies after something else
    (e.g. alembic's fileConfig) replaced the root handlers."""
    global _configured
    if _configured and not force:
        return
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if as_json else PlainFormatter())
    handler.addFilter(RedactingFilter())
    root.handlers = [handler]
    # quiet noisy libraries
    for name in ("httpx", "httpcore", "hpack", "telegram", "apscheduler", "asyncio", "minio"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str, **context: Any) -> ContextLoggerAdapter:
    logger = logging.getLogger(name)
    return ContextLoggerAdapter(logger, context)
