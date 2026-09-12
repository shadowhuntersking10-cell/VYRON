"""Telegram initData HMAC validation — the only way Mini App sessions are issued."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse

import pytest

TOKEN = "123456:TEST-BOT-TOKEN"


def build_init_data(token: str = TOKEN, user_id: int = 42, username: str = "tester", auth_date: int | None = None, start_param: str | None = None) -> str:
    user = {"id": user_id, "first_name": "Test", "username": username, "language_code": "en"}
    params = {"user": json.dumps(user, separators=(",", ":")), "auth_date": str(auth_date or int(time.time()))}
    if start_param:
        params["start_param"] = start_param
    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    sign = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode({**params, "hash": sign})


def test_valid_init_data_accepted():
    from vyron.security.telegram_auth import validate_init_data

    parsed = validate_init_data(build_init_data(), bot_token=TOKEN)
    assert parsed.user is not None
    assert parsed.user.id == 42
    assert parsed.user.username == "tester"


def test_tampered_init_data_rejected():
    from vyron.security.telegram_auth import TelegramAuthError, validate_init_data

    tampered = build_init_data().replace("tester", "hacker")
    with pytest.raises(TelegramAuthError):
        validate_init_data(tampered, bot_token=TOKEN)


def test_stale_init_data_rejected():
    from vyron.security.telegram_auth import TelegramAuthError, validate_init_data

    old = build_init_data(auth_date=int(time.time()) - 99999)
    with pytest.raises(TelegramAuthError):
        validate_init_data(old, bot_token=TOKEN, max_age=3600)


def test_wrong_bot_token_rejected():
    from vyron.security.telegram_auth import TelegramAuthError, validate_init_data

    with pytest.raises(TelegramAuthError):
        validate_init_data(build_init_data(), bot_token="999:WRONG")


def test_missing_token_is_config_error_not_silent_pass():
    from vyron.security.telegram_auth import TelegramAuthError, validate_init_data

    with pytest.raises(TelegramAuthError) as exc:
        validate_init_data(build_init_data(), bot_token="")
    assert "configured" in str(exc.value).lower()


def test_start_param_survives_parsing():
    from vyron.security.telegram_auth import validate_init_data

    parsed = validate_init_data(build_init_data(start_param="abc123"), bot_token=TOKEN)
    assert parsed.start_param == "abc123"


def test_api_rejects_garbage_init_data(client, csrf):
    res = client.post("/api/telegram/auth", json={"init_data": "query_id=x&user=y&hash=bad"})
    assert res.status_code in (400, 401, 403, 503)
    assert res.json()["success"] is False
    assert res.json()["error"]["code"] in ("TELEGRAM_NOT_CONFIGURED", "TELEGRAM_INIT_DATA_INVALID")


def test_admin_gate_is_env_driven():
    from vyron.config import settings
    from vyron.security.telegram_auth import is_telegram_admin_id

    configured = set(settings.admin_telegram_id_list)
    for tid in configured:
        assert is_telegram_admin_id(tid) is True
    assert is_telegram_admin_id(-12345) is False
