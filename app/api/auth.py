"""Auth API: register/login/logout/reset + Telegram WebApp login."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app import models
from app.auth.service import AuthError, AuthService, grant_role
from app.auth.telegram import TelegramAuth
from app.config import settings
from app.database import SessionLocal
from app.dependencies import Db, get_lang, require_user, user_roles
from app.schemas import ForgotIn, LoginIn, RegisterIn, ResetIn, UserOut
from app.utils.security import new_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session(response: Response, token: str, csrf: str):
    secure = settings.is_production
    response.set_cookie(settings.SESSION_COOKIE, token, httponly=True, secure=secure,
                        samesite="lax", max_age=settings.SESSION_TTL_HOURS * 3600, path="/")
    response.set_cookie(settings.CSRF_COOKIE, csrf, httponly=False, secure=secure,
                        samesite="lax", max_age=settings.SESSION_TTL_HOURS * 3600, path="/")


def _user_out(user: models.User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email,
                   display_name=user.display_name or "", avatar=user.avatar or "",
                   lang=user.lang, theme=user.theme, roles=sorted(user_roles(user)))


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Db, lang: str = "uz"):
    svc = AuthService(db)
    try:
        user = svc.register(body.username, body.email, body.password, body.password_confirm,
                            lang=get_lang(request))
    except AuthError as e:
        raise HTTPException(status_code=400, detail=e.key)
    sess = svc.create_session(user, ip=request.client.host if request.client else "", ua=request.headers.get("user-agent", ""))
    _set_session(response, sess.token, sess.csrf_token)
    return {"user": _user_out(user)}


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Db):
    svc = AuthService(db)
    try:
        user, sess = svc.login(body.login, body.password,
                               ip=request.client.host if request.client else "",
                               ua=request.headers.get("user-agent", ""))
    except AuthError as e:
        raise HTTPException(status_code=400, detail=e.key)
    _set_session(response, sess.token, sess.csrf_token)
    return {"user": _user_out(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Db):
    token = request.cookies.get(settings.SESSION_COOKIE, "")
    AuthService(db).logout(token)
    response.delete_cookie(settings.SESSION_COOKIE, path="/")
    response.delete_cookie(settings.CSRF_COOKIE, path="/")
    return {"ok": True}


@router.post("/forgot")
def forgot(body: ForgotIn, db: Db):
    try:
        token = AuthService(db).forgot_password(body.email)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=e.key)
    # In production the token is emailed; in dev we return a hint-free response.
    out = {"ok": True}
    if not settings.is_production and token:
        out["dev_reset_token"] = token
    return out


@router.post("/reset")
def reset(body: ResetIn, db: Db):
    try:
        user = AuthService(db).reset_password(body.token, body.password, body.password_confirm)
    except AuthError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return {"ok": True, "username": user.username}


@router.get("/verify-email")
def verify_email(token: str, db: Db):
    ok = AuthService(db).verify_email(token)
    if not ok:
        raise HTTPException(status_code=400, detail="invalid_token")
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Db):
    user = getattr(request.state, "user", None)
    if not user:
        return {"user": None}
    return {"user": _user_out(user)}


class TelegramLoginIn(BaseModel):
    init_data: str = ""


@router.post("/telegram")
def telegram_login(body: TelegramLoginIn, request: Request, response: Response, db: Db):
    """Validate Telegram initData server-side, link/create user, grant admin by env IDs."""
    data = TelegramAuth(settings.TELEGRAM_BOT_TOKEN).validate(body.init_data)
    if not data or "user" not in data:
        raise HTTPException(status_code=401, detail="invalid_telegram_auth")
    tg_user = data["user"]
    tg_id = int(tg_user.get("id", 0))
    if not tg_id:
        raise HTTPException(status_code=401, detail="invalid_telegram_auth")
    tg = db.query(models.TelegramUser).filter_by(telegram_id=tg_id).first()
    is_admin = tg_id in settings.admin_telegram_ids
    if not tg:
        tg = models.TelegramUser(telegram_id=tg_id, username=tg_user.get("username", "") or "",
                                 first_name=tg_user.get("first_name", "") or "",
                                 last_name=tg_user.get("last_name", "") or "",
                                 language_code=tg_user.get("language_code", "") or "",
                                 is_admin=is_admin)
        db.add(tg)
        db.flush()
    else:
        tg.is_admin = is_admin
    user = db.query(models.User).filter_by(id=tg.user_id).first() if tg.user_id else None
    if not user:
        # create a linked user account (random secure password; login via Telegram)
        uname = (tg.username or f"tg{tg_id}")[:32]
        base, i = uname, 0
        while db.query(models.User).filter_by(username=uname).first():
            i += 1
            uname = f"{base[:28]}{i}"
        from app.utils.security import hash_password
        user = models.User(username=uname, email=f"tg{tg_id}@vyron.telegram",
                           password_hash=hash_password(new_token()),
                           display_name=tg.first_name or uname, lang=get_lang(request))
        db.add(user)
        db.flush()
        grant_role(db, user, "user")
        db.add(models.Wallet(user_id=user.id))
        tg.user_id = user.id
    if is_admin:
        grant_role(db, user, "admin")
    db.commit()
    svc = AuthService(db)
    sess = svc.create_session(user, ip=request.client.host if request.client else "", ua="telegram-miniapp")
    _set_session(response, sess.token, sess.csrf_token)
    return {"user": _user_out(user)}
