"""VYRON security package: hashing, crypto, sessions, CSRF, rate limiting, RBAC,
Telegram initData validation and security headers."""

from vyron.security.crypto import decrypt_json, decrypt_str, encrypt_json, encrypt_str, mask_secret
from vyron.security.hashing import generate_token, hash_password, hash_token, verify_password
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import (
    get_current_user,
    get_optional_user,
    require_admin,
    require_finance,
    require_moderator,
    require_roles,
    require_staff,
    require_super_admin,
)
from vyron.security.sessions import create_session, get_session_user, revoke_all_user_sessions, revoke_session
from vyron.security.telegram_auth import validate_init_data

__all__ = [
    "create_session",
    "decrypt_json",
    "decrypt_str",
    "encrypt_json",
    "encrypt_str",
    "enforce_rate_limit",
    "generate_token",
    "get_current_user",
    "get_optional_user",
    "get_session_user",
    "hash_password",
    "hash_token",
    "mask_secret",
    "require_admin",
    "require_finance",
    "require_moderator",
    "require_roles",
    "require_staff",
    "require_super_admin",
    "revoke_all_user_sessions",
    "revoke_session",
    "validate_init_data",
    "verify_password",
]
