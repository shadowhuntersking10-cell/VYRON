import time

import pytest

from app.auth.telegram_auth import TelegramAuthError, build_init_data_for_tests, validate_telegram_init_data

BOT = "test-bot-token-123"


def test_valid_init_data():
    user = {"id": 777, "first_name": "Test", "username": "tester"}
    init_data = build_init_data_for_tests(user, BOT)
    payload = validate_telegram_init_data(init_data, BOT)
    assert payload["user"]["id"] == 777


def test_tampered_signature_rejected():
    user = {"id": 777, "first_name": "Test"}
    init_data = build_init_data_for_tests(user, BOT)
    tampered = init_data.replace("Test", "Hacker")
    with pytest.raises(TelegramAuthError):
        validate_telegram_init_data(tampered, BOT)


def test_expired_rejected():
    user = {"id": 777}
    init_data = build_init_data_for_tests(user, BOT, auth_date=int(time.time()) - 999999)
    with pytest.raises(TelegramAuthError):
        validate_telegram_init_data(init_data, BOT, max_age_seconds=60)


def test_wrong_token_rejected():
    user = {"id": 777}
    init_data = build_init_data_for_tests(user, BOT)
    with pytest.raises(TelegramAuthError):
        validate_telegram_init_data(init_data, "other-token")
