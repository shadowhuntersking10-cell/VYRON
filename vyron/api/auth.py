"""Auth API: register, login, logout, me, verify-email, forgot/reset password.

All sensitive endpoints are rate limited (Redis) and audited.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.config import settings
from vyron.db.base import get_db
from vyron.db.models import User
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user, get_optional_user
from vyron.security.sessions import client_ip, create_session, revoke_all_user_sessions, revoke_session
from vyron.services import auth_service, telegram_service
from vyron.web.serializers import user_public

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]{3,30}$")
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)
    locale: Optional[str] = Field(default=None, pattern=r"^(uz|en|ru)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotRequest(BaseModel):
    email: EmailStr


class ResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)


@router.post("/register")
def register(payload: RegisterRequest, request: Request, response: Response, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "register", settings.rate_limit_register)
    user = auth_service.register_user(
        db,
        name=payload.name,
        username=payload.username,
        email=str(payload.email),
        password=payload.password,
        confirm_password=payload.confirm_password,
        phone=payload.phone,
        locale=payload.locale or "uz",
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    create_session(db, user, request, response)
    return ok(user_public(user), message_code="AUTH_REGISTERED")


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "login", settings.rate_limit_login)
    user = auth_service.login_user(
        db,
        email=str(payload.email),
        password=payload.password,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    create_session(db, user, request, response)
    return ok(user_public(user), message_code="AUTH_LOGGED_IN")


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession = Depends(get_db)):
    revoke_session(db, request, response)
    return ok(message_code="AUTH_LOGGED_OUT")


@router.get("/me")
def me(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    if user is None:
        return ok(None)
    connection = telegram_service.connection_for_user(db, user)
    data = user_public(user)
    data["telegram_connected"] = connection is not None
    data["telegram_username"] = connection.telegram_username if connection else None
    data["is_admin"] = telegram_service.is_admin_context(db, user, connection.telegram_id if connection else 0)
    return ok(data)


@router.post("/verify-email")
def verify_email(payload: VerifyRequest, request: Request, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "verify", settings.rate_limit_reset)
    user = auth_service.verify_email(db, payload.token)
    return ok(user_public(user), message_code="EMAIL_VERIFIED")


@router.post("/verify-email/resend")
def resend_verification(request: Request, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    enforce_rate_limit(request, "verify-resend", settings.rate_limit_reset, user_id=user.id)
    auth_service.resend_verification(db, user)
    return ok(message_code="VERIFICATION_SENT")


@router.post("/forgot-password")
def forgot_password(payload: ForgotRequest, request: Request, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "forgot", settings.rate_limit_reset)
    token = auth_service.forgot_password(db, str(payload.email))
    result = ok(message_code="RESET_SENT")
    if token:  # development convenience ONLY (never returned in production)
        result["dev_token"] = token
    return result


@router.post("/reset-password")
def reset_password(payload: ResetRequest, request: Request, db: DbSession = Depends(get_db)):
    enforce_rate_limit(request, "reset", settings.rate_limit_reset)
    auth_service.reset_password(db, payload.token, payload.new_password, payload.confirm_password)
    return ok(message_code="PASSWORD_RESET")


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest, request: Request, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)
):
    enforce_rate_limit(request, "change-password", settings.rate_limit_reset, user_id=user.id)
    auth_service.change_password(db, user, payload.current_password, payload.new_password, payload.confirm_password)
    return ok(message_code="PASSWORD_CHANGED")


@router.get("/telegram/link-token")
def telegram_link_token(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(telegram_service.get_link_token(db, user))


@router.post("/telegram/unlink")
def telegram_unlink(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    telegram_service.unlink_account(db, user)
    return ok(message_code="TELEGRAM_UNLINKED")


@router.post("/logout-all")
def logout_all(request: Request, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):

    revoke_all_user_sessions(db, user.id)
    return ok(message_code="SESSIONS_REVOKED")
