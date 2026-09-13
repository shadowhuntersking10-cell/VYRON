"""Password hashing (bcrypt) + session helpers."""
from __future__ import annotations

import bcrypt


def hash_password(password: str) -> str:
    if len(password.encode()) > 72:
        raise ValueError("Password too long (max 72 bytes)")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


COMMON_PASSWORDS = frozenset({
    "password", "password1", "12345678", "qwerty123", "letmein1", "welcome1",
    "admin123", "vyron123", "iloveyou", "football", "monkey123",
})


def check_password_strength(password: str) -> list[str]:
    """Return a list of unmet strength rules (empty = strong enough)."""
    problems: list[str] = []
    if len(password) < 10:
        problems.append("min_length_10")
    classes = sum((
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ))
    if classes < 3:
        problems.append("need_3_of_4_classes")
    if password.strip().lower() in COMMON_PASSWORDS:
        problems.append("too_common")
    return problems
