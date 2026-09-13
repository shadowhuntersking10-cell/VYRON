"""Email/username auth: register / login / logout / sessions / reset / verify."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginIn, RegisterIn, UserOut
from app.services import auth_service, email_service
from app.utils.helpers import client_ip
from app.utils.ratelimit import check_rate_limit

log = logging.getLogger("vyron.auth")

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
        user = await auth_service.authenticate(db, data.login, data.password, ip=client_ip(request.headers))
        token = await auth_service.create_session(db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request.headers))
        await db.commit()
    except auth_service.AuthError as exc:
        await db.rollback()
        code = status.HTTP_429_TOO_MANY_REQUESTS if str(exc) == "too_many_attempts" else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(code, str(exc)) from exc
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


class ForgotIn(BaseModel):
    login: str = Field(min_length=2, max_length=255)


@router.post("/forgot")
async def forgot_password(data: ForgotIn, request: Request, db: AsyncSession = Depends(get_db)):
    """Request a password reset link. Always returns ok (no account probing)."""
    ok, retry = check_rate_limit(f"forgot:{client_ip(request.headers)}", max(5, settings.RATE_LIMIT_PER_MINUTE // 6))
    if not ok:
        raise HTTPException(429, f"rate_limited:{retry}")
    delivered: bool | None = None
    user = await auth_service.get_user_by_login(db, data.login)
    if user and user.email:
        token = await auth_service.create_password_reset(db, user)
        await db.commit()
        reset_url = f"{settings.APP_BASE_URL.rstrip('/')}/auth/login?reset=1&token={token}"
        sent, reason = await email_service.send_email(
            user.email, "VYRON password reset",
            f"Reset your VYRON password (valid {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes):\n{reset_url}\n\n"
            "If you didn't ask for this, ignore this email.")
        delivered = sent
        if not sent:
            log.warning("reset email not delivered to %s: %s", user.email, reason)
    elif user:
        delivered = False
    return {"ok": True, "email_sent": delivered}


class ResetIn(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=72)
    password_confirm: str = Field(min_length=8, max_length=72)


@router.post("/reset")
async def reset_password(data: ResetIn, request: Request, db: AsyncSession = Depends(get_db)):
    ok, retry = check_rate_limit(f"reset:{client_ip(request.headers)}", max(10, settings.RATE_LIMIT_PER_MINUTE // 3))
    if not ok:
        raise HTTPException(429, f"rate_limited:{retry}")
    if data.password != data.password_confirm:
        raise HTTPException(400, "passwords_do_not_match")
    try:
        user = await auth_service.consume_password_reset(db, data.token, data.password)
        await db.commit()
    except auth_service.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "login": user.email or user.username}


@router.post("/verify/request")
async def verify_request(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.email_verified:
        return {"ok": True, "already": True}
    if not user.email:
        raise HTTPException(400, "email_required")
    token = await auth_service.create_email_verification(db, user)
    await db.commit()
    verify_url = f"{settings.APP_BASE_URL.rstrip('/')}/app/settings?verify={token}"
    sent, reason = await email_service.send_email(
        user.email, "Verify your VYRON email",
        f"Confirm your email address (valid 24 hours):\n{verify_url}")
    if not sent:
        log.warning("verify email not delivered to %s: %s", user.email, reason)
    return {"ok": True, "email_sent": sent, **({} if sent else {"detail": reason})}


class VerifyIn(BaseModel):
    token: str = Field(min_length=10)


@router.post("/verify/confirm")
async def verify_confirm(data: VerifyIn, db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.consume_email_verification(db, data.token)
        await db.commit()
    except auth_service.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "email_verified": user.email_verified}
