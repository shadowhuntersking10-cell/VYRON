"""Small shared helpers."""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_public_id(prefix: str = "VYR") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def client_ip(headers: dict, fallback: str = "") -> str:
    for key in ("x-forwarded-for", "x-real-ip"):
        val = headers.get(key) or headers.get(key.title())
        if val:
            return val.split(",")[0].strip()
    return fallback
