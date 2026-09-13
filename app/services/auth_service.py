"""Registration, login, sessions, password reset, email verification."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.config import settings
from app.models import PasswordResetToken, User, UserRole, UserSession
from app.utils.helpers import generate_token, hash_token, utcnow


class AuthError(ValueError):
    pass


async def get_user_by_login(db: AsyncSession, login: str) -> User | None:
    login = login.strip()
    stmt = select(User).where((User.email == login) | (User.username == login)).limit(1)
    return (await db.execute(stmt)).scalars().first()


async def register_user(
    db: AsyncSession,
    *,
    email: str | None,
    username: str | None,
    password: str,
    full_name: str | None = None,
    lang: str = "uz",
) -> User:
    email = (email or "").strip().lower() or None
    username = (username or "").strip() or None
    if not email and not username:
        raise AuthError("email_or_username_required")
    if email:
        exists = (await db.execute(select(User).where(User.email == email))).scalars().first()
        if exists:
            raise AuthError("email_taken")
    if username:
        exists = (await db.execute(select(User).where(User.username == username))).scalars().first()
        if exists:
            raise AuthError("username_taken")
    user = User(
        email=email,
        username=username or (email.split("@")[0] if email else None),
        password_hash=hash_password(password),
        full_name=full_name,
        role=UserRole.USER,
        lang=lang if lang in ("uz", "en", "ru") else "uz",
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate(db: AsyncSession, login: str, password: str) -> User:
    user = await get_user_by_login(db, login)
    if not user or not verify_password(password, user.password_hash):
        raise AuthError("invalid_credentials")
    if user.is_banned:
        raise AuthError("user_banned")
    if not user.is_active:
        raise AuthError("user_inactive")
    user.last_login_at = utcnow()
    await db.flush()
    return user


async def create_session(
    db: AsyncSession, user: User, *, user_agent: str | None = None, ip: str | None = None
) -> str:
    token = generate_token()
    expires = utcnow() + dt.timedelta(days=settings.SESSION_EXPIRE_DAYS)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            user_agent=(user_agent or "")[:500],
            ip_address=(ip or "")[:64],
            expires_at=expires,
        )
    )
    await db.flush()
    return token


async def revoke_session(db: AsyncSession, token: str) -> None:
    stmt = select(UserSession).where(UserSession.token_hash == hash_token(token))
    sess = (await db.execute(stmt)).scalars().first()
    if sess:
        sess.revoked = True
        await db.flush()


async def revoke_all_sessions(db: AsyncSession, user_id: int) -> int:
    stmt = select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked.is_(False))
    rows = (await db.execute(stmt)).scalars().all()
    for r in rows:
        r.revoked = True
    await db.flush()
    return len(rows)


async def change_password(db: AsyncSession, user: User, old_password: str, new_password: str) -> None:
    if not verify_password(old_password, user.password_hash):
        raise AuthError("wrong_password")
    user.password_hash = hash_password(new_password)
    await revoke_all_sessions(db, user.id)


async def create_password_reset(db: AsyncSession, user: User) -> str:
    """Returns raw token (to be emailed). Architecture ready; SMTP optional."""
    token = generate_token()
    expires = utcnow() + dt.timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    db.add(PasswordResetToken(user_id=user.id, token_hash=hash_token(token), expires_at=expires))
    await db.flush()
    return token


async def consume_password_reset(db: AsyncSession, token: str, new_password: str) -> User:
    stmt = select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    rec = (await db.execute(stmt)).scalars().first()
    if not rec or rec.used:
        raise AuthError("invalid_token")
    exp = rec.expires_at if rec.expires_at.tzinfo else rec.expires_at.replace(tzinfo=dt.timezone.utc)
    if exp < utcnow():
        raise AuthError("token_expired")
    user = await db.get(User, rec.user_id)
    if not user:
        raise AuthError("user_not_found")
    user.password_hash = hash_password(new_password)
    rec.used = True
    await revoke_all_sessions(db, user.id)
    return user
