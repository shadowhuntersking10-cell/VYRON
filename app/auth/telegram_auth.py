"""Telegram WebApp initData validation (per official Telegram docs).

Never trust client-provided telegram user data without HMAC verification.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(ValueError):
    pass


def validate_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> dict:
    """Validate initData signature; return the parsed payload (incl. `user` dict)."""
    if not init_data or not bot_token:
        raise TelegramAuthError("Missing init data or bot token")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise TelegramAuthError("Missing hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise TelegramAuthError("Invalid signature")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise TelegramAuthError("Invalid auth_date") from None
    if max_age_seconds > 0 and (time.time() - auth_date) > max_age_seconds:
        raise TelegramAuthError("initData expired")

    payload = dict(pairs)
    if "user" in payload and isinstance(payload["user"], str):
        try:
            payload["user"] = json.loads(payload["user"])
        except json.JSONDecodeError:
            raise TelegramAuthError("Invalid user payload") from None
    if not isinstance(payload.get("user"), dict) or "id" not in payload["user"]:
        raise TelegramAuthError("Missing Telegram user")
    return payload


def build_init_data_for_tests(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """Helper used by tests to craft correctly-signed initData."""
    import urllib.parse

    auth_date = auth_date or int(time.time())
    pairs = {
        "auth_date": str(auth_date),
        "query_id": "test-query",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    sig = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    pairs["hash"] = sig
    return urllib.parse.urlencode(pairs)
