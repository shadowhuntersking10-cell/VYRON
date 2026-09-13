"""Auth dependencies: session cookie -> current user, RBAC guards."""
from __future__ import annotations

import datetime as dt

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, UserRole, UserSession
from app.utils.helpers import hash_token


async def _user_from_token(session: AsyncSession, token: str | None) -> User | None:
    if not token:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    # normalize: stored datetimes may be naive depending on backend
    stmt = (
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token), UserSession.revoked.is_(False))
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    sess, user = row
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=dt.timezone.utc)
    if exp < now:
        return None
    if user.is_banned or not user.is_active:
        return None
    return user


def _extract_token(request: Request) -> str | None:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


async def get_current_user_optional(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User | None:
    return await _user_from_token(db, _extract_token(request))


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    user = await _user_from_token(db, _extract_token(request))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth_required")
    return user


def require_roles(*roles: UserRole):
    async def _guard(user: User = Depends(get_current_user)) -> User:
        # ADMIN bypasses role checks
        if user.role == UserRole.ADMIN:
            return user
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return _guard


require_user = require_roles(UserRole.USER, UserRole.SELLER, UserRole.ADMIN)
require_seller = require_roles(UserRole.SELLER, UserRole.ADMIN)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_only")
    return user
