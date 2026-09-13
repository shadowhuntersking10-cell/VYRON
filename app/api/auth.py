"""Email/username auth: register / login / logout / sessions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginIn, RegisterIn, UserOut
from app.services import auth_service
from app.utils.helpers import client_ip
from app.utils.ratelimit import check_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_KWARGS = {"httponly": True, "samesite": "lax", "path": "/"}


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE_NAME, token,
        max_age=settings.SESSION_EXPIRE_DAYS * 86400,
        secure=settings.is_production, **COOKIE_KWARGS,
    )


@router.post("/register", response_model=UserOut)
async def register(data: RegisterIn, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    ok, retry = check_rate_limit(f"register:{client_ip(request.headers)}", settings.RATE_LIMIT_PER_MINUTE)
    if not ok:
        raise HTTPException(429, f"rate_limited:{retry}")
    try:
        user = await auth_service.register_user(
            db, email=str(data.email) if data.email else None,
            username=data.username, password=data.password,
            full_name=data.full_name, lang=data.lang,
        )
        token = await auth_service.create_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request.headers))
        await db.commit()
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _set_session_cookie(response, token)
    return user


@router.post("/login", response_model=UserOut)
async def login(data: LoginIn, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    ok, retry = check_rate_limit(f"login:{client_ip(request.headers)}", settings.RATE_LIMIT_PER_MINUTE)
    if not ok:
        raise HTTPException(429, f"rate_limited:{retry}")
    try:
        user = await auth_service.authenticate(db, data.login, data.password)
        token = await auth_service.create_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request.headers))
        await db.commit()
    except auth_service.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    _set_session_cookie(response, token)
    return user


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if token:
        await auth_service.revoke_session(db, token)
        await db.commit()
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
