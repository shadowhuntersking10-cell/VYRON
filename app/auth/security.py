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
