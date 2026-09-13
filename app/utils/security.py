"""Security helpers: password hashing (PBKDF2), tokens, CSRF, rate limiting."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_ITERATIONS = 210_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    try:
        _, iters, salt, hexdk = hashed.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return hmac.compare_digest(dk.hex(), hexdk)
    except Exception:
        return False


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip().lower()))


def validate_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(username or ""))


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Returns (ok, error_key)."""
    if not password or len(password) < 8:
        return False, "password_too_weak"
    if len(password) > 128:
        return False, "password_too_weak"
    checks = [
        re.search(r"[a-z]", password),
        re.search(r"[A-Z]", password),
        re.search(r"[0-9]", password),
    ]
    if sum(1 for c in checks if c) < 2:
        return False, "password_too_weak"
    return True, ""


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


class RateLimiter:
    """In-memory sliding-window rate limiter (per key)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        q = self._hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


rate_limiter = RateLimiter()
