"""Secure cookie sessions backed by the DB (revocable, expiring).

Cookie: `vyron_session` — HttpOnly, SameSite=Lax, Secure in production.
The DB stores only the SHA-256 hash of the token, so a database leak does not
leak usable sessions.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import Request, Response
from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.base import utcnow
from vyron.db.models import Session as SessionModel
from vyron.db.models import User
from vyron.enums import UserStatus
from vyron.security.hashing import generate_token, hash_token

COOKIE_NAME = "vyron_session"


def _cookie_kwargs(max_age: int) -> dict:
    return {
        "key": COOKIE_NAME,
        "max_age": max_age,
        "httponly": True,
        "secure": settings.is_production,
        "samesite": "lax",
        "path": "/",
    }


def create_session(db: DbSession, user: User, request: Request, response: Response) -> str:
    token = generate_token(48)
    ttl = timedelta(days=settings.session_ttl_days)
    session = SessionModel(
        user_id=user.id,
        token_hash=hash_token(token),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        ip_address=client_ip(request),
        expires_at=utcnow() + ttl,
    )
    db.add(session)
    db.commit()
    response.set_cookie(value=token, **_cookie_kwargs(int(ttl.total_seconds())))
    return token


def get_session_user(db: DbSession, request: Request) -> Optional[User]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    digest = hash_token(token)
    session = db.query(SessionModel).filter(SessionModel.token_hash == digest).first()
    if session is None or not session.is_active:
        return None
    user: Optional[User] = db.get(User, session.user_id)
    if user is None or user.status != UserStatus.ACTIVE.value:
        return None
    # Sliding expiration: extend once past half the TTL.
    remaining = (session.expires_at - utcnow()).total_seconds()
    if remaining < settings.session_ttl_days * 86400 / 2:
        session.expires_at = utcnow() + timedelta(days=settings.session_ttl_days)
        db.commit()
    return user


def revoke_session(db: DbSession, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.query(SessionModel).filter(SessionModel.token_hash == hash_token(token)).update(
            {"revoked_at": utcnow()}, synchronize_session=False
        )
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


def revoke_all_user_sessions(db: DbSession, user_id: str, except_token: Optional[str] = None) -> int:
    query = db.query(SessionModel).filter(
        SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None)
    )
    if except_token:
        query = query.filter(SessionModel.token_hash != hash_token(except_token))
    count = query.update({"revoked_at": utcnow()}, synchronize_session=False)
    db.commit()
    return count


def cleanup_expired_sessions(db: DbSession) -> int:
    cutoff = utcnow() - timedelta(days=1)
    count = db.query(SessionModel).filter(SessionModel.expires_at < cutoff).delete(synchronize_session=False)
    db.commit()
    return count


def client_ip(request: Request) -> Optional[str]:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.client.host[:64] if request.client else None)
