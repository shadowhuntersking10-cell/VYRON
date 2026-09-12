"""Telegram Web App `initData` authentication (official algorithm).

https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

1. Parse the query-string style initData payload.
2. Build data_check_string: all fields except `hash`, sorted alphabetically,
   joined with '\\n' as `key=value`.
3. secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
4. Compare HMAC_SHA256(key=secret_key, msg=data_check_string) with `hash`.
5. Reject stale auth_date (replay protection).

The result: a cryptographically verified Telegram user identity. Admin status
is then checked SERVER-SIDE against ADMIN_TELEGRAM_IDS and/or the linked
VYRON account role — never from frontend claims.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, unquote

from vyron.config import settings
from vyron.errors import AuthError
from vyron.logging import get_logger

log = get_logger("vyron.telegram_auth")

MAX_AUTH_AGE_SECONDS = 86400  # 24h


class TelegramAuthError(AuthError):
    code = "TELEGRAM_INIT_DATA_INVALID"
    default_message = "Telegram authentication failed."


@dataclass
class TelegramUser:
    id: int
    first_name: str = ""
    last_name: str = ""
    username: str = ""
    language_code: str = ""
    is_premium: bool = False
    photo_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InitData:
    query_id: Optional[str]
    user: Optional[TelegramUser]
    auth_date: int
    start_param: Optional[str]
    chat_instance: Optional[str]
    chat_type: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict)


def validate_init_data(init_data: str, bot_token: Optional[str] = None, max_age: int = MAX_AUTH_AGE_SECONDS) -> InitData:
    token = bot_token or settings.telegram_bot_token
    if not token:
        raise TelegramAuthError("Telegram bot token is not configured on the server.", code="TELEGRAM_NOT_CONFIGURED")
    if not init_data:
        raise TelegramAuthError("initData is empty.")

    try:
        pairs = parse_qsl(init_data, strict_parsing=True)
    except ValueError as exc:
        raise TelegramAuthError("initData is malformed.") from exc

    data: Dict[str, str] = {k: v for k, v in pairs}
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("initData is missing hash.")

    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        log.warning("initData signature mismatch")
        raise TelegramAuthError("initData signature is invalid.")

    auth_date = int(data.get("auth_date", "0"))
    if max_age and (time.time() - auth_date) > max_age:
        raise TelegramAuthError("initData is too old (possible replay).")

    user: Optional[TelegramUser] = None
    if "user" in data:
        try:
            u = json.loads(unquote(data["user"])) if "%" in data["user"] else json.loads(data["user"])
            user = TelegramUser(
                id=int(u["id"]),
                first_name=u.get("first_name", ""),
                last_name=u.get("last_name", ""),
                username=u.get("username", ""),
                language_code=u.get("language_code", ""),
                is_premium=bool(u.get("is_premium", False)),
                photo_url=u.get("photo_url", ""),
                raw=u,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise TelegramAuthError("initData user payload is invalid.") from exc

    parsed: Dict[str, Any] = dict(data)
    for key in ("user", "receiver", "chat"):
        if key in parsed:
            try:
                parsed[key] = json.loads(parsed[key])
            except (ValueError, TypeError):
                pass

    return InitData(
        query_id=data.get("query_id"),
        user=user,
        auth_date=auth_date,
        start_param=data.get("start_param"),
        chat_instance=data.get("chat_instance"),
        chat_type=data.get("chat_type"),
        raw=parsed,
    )


def is_telegram_admin_id(telegram_id: int) -> bool:
    """Server-side admin gate #1: ADMIN_TELEGRAM_IDS configuration."""
    return telegram_id in settings.admin_telegram_id_list
