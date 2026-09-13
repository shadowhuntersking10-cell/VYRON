from __future__ import annotations
from typing import Optional
from fastapi import Depends, Request, HTTPException, status, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.models import User, UserSession, Role, UserRole
from app.config import settings
from app.utils.security import decode_jwt_token
from datetime import datetime

async def get_current_user_optional(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    token = session_token
    # Also check Authorization header
    if not token:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.replace("Bearer ", "")
    
    if not token:
        # Check cookie named session
        token = request.cookies.get("session_token") or request.cookies.get("session")
    
    if not token:
        return None

    # Try JWT first
    payload = decode_jwt_token(token)
    if payload:
        user_id = payload.get("user_id")
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user and user.status == "ACTIVE":
                return user

    # Try session table
    result = await db.execute(
        select(UserSession).where(
            UserSession.session_token == token,
            UserSession.is_valid == True,
            UserSession.expires_at > datetime.utcnow()
        )
    )
    session = result.scalar_one_or_none()
    if session:
        result = await db.execute(select(User).where(User.id == session.user_id))
        user = result.scalar_one_or_none()
        if user and user.status == "ACTIVE":
            return user

    return None

async def get_current_user(
    current_user: Optional[User] = Depends(get_current_user_optional)
) -> User:
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return current_user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> User:
    if current_user.is_admin:
        return current_user
    
    # Check roles
    result = await db.execute(
        select(Role).join(UserRole).where(
            UserRole.user_id == current_user.id,
            Role.name == "admin"
        )
    )
    role = result.scalar_one_or_none()
    if role:
        return current_user
    
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

async def get_current_user_from_telegram(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    # For Telegram Mini App, validate initData
    init_data = request.headers.get("X-Telegram-Init-Data") or request.headers.get("X-Telegram-InitData")
    if not init_data:
        # Try to get from query param or body? For now return None
        return None
    
    from app.utils.security import verify_telegram_init_data
    is_valid, user_data, error = verify_telegram_init_data(init_data, settings.TELEGRAM_BOT_TOKEN or "")
    if not is_valid:
        return None
    
    telegram_id = user_data.get("id")
    if not telegram_id:
        return None
    
    from sqlalchemy import select
    from app.models.models import TelegramUser
    result = await db.execute(select(TelegramUser).where(TelegramUser.telegram_id == telegram_id))
    tg_user = result.scalar_one_or_none()
    if tg_user and tg_user.user_id:
        result = await db.execute(select(User).where(User.id == tg_user.user_id))
        return result.scalar_one_or_none()
    
    return None

# Rate limiting simple in-memory (should use Redis in production)
from collections import defaultdict
import time

_rate_limit_store = defaultdict(list)

def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    def dependency(request: Request):
        if settings.REDIS_URL:
            # TODO: Use Redis for rate limiting
            pass
        
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{request.url.path}"
        now = time.time()
        
        # Clean old entries
        _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window_seconds]
        
        if len(_rate_limit_store[key]) >= max_requests:
            raise HTTPException(status_code=429, detail="Too many requests")
        
        _rate_limit_store[key].append(now)
    
    return dependency
