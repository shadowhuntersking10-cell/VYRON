"""Password hashing (Argon2id) and token hashing (SHA-256).

Plaintext passwords never touch the database or logs. Password hashes are
never serialized in any API response (enforced by response schemas).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)  # argon2id by default


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


def generate_token(nbytes: int = 48) -> str:
    """URL-safe random token (sessions, verification, linking, idempotency)."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Only SHA-256 digests of tokens are stored server-side."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
