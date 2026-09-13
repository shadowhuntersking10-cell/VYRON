"""Real authentication: register / login / sessions / password reset."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.utils.i18n import t
from app.utils.logging import get_logger
from app.utils.security import (
    hash_password,
    new_token,
    rate_limiter,
    validate_email,
    validate_password_strength,
    validate_username,
    verify_password,
)

log = get_logger("vyron.auth")


class AuthError(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


def _ensure_role(db: Session, name: str) -> models.Role:
    role = db.query(models.Role).filter_by(name=name).first()
    if not role:
        role = models.Role(name=name)
        db.add(role)
        db.flush()
    return role


def grant_role(db: Session, user: models.User, name: str) -> None:
    _ensure_role(db, name)
    if name not in {ur.role.name for ur in user.roles}:
        role = db.query(models.Role).filter_by(name=name).first()
        db.add(models.UserRole(user_id=user.id, role_id=role.id))


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    # ----- registration -----
    def register(self, username: str, email: str, password: str, password_confirm: str,
                 lang: str = "uz") -> models.User:
        username = (username or "").strip()
        email = (email or "").strip().lower()
        if not validate_username(username):
            raise AuthError("invalid_username")
        if not validate_email(email):
            raise AuthError("invalid_email")
        if password != password_confirm:
            raise AuthError("password_mismatch")
        ok, key = validate_password_strength(password)
        if not ok:
            raise AuthError(key)
        if not rate_limiter.allow(f"register:{email}", 5, 3600):
            raise AuthError("too_many_attempts")
        if self.db.query(models.User).filter_by(username=username).first():
            raise AuthError("username_exists")
        if self.db.query(models.User).filter_by(email=email).first():
            raise AuthError("email_exists")
        user = models.User(
            username=username, email=email, password_hash=hash_password(password),
            display_name=username, lang=lang,
            email_verify_token=new_token(24),
        )
        self.db.add(user)
        self.db.flush()
        grant_role(self.db, user, "user")
        # wallet
        self.db.add(models.Wallet(user_id=user.id))
        self.db.commit()
        log.info("registered user id=%s username=%s", user.id, username)
        return user

    # ----- login -----
    def login(self, login: str, password: str, ip: str = "", ua: str = "") -> tuple[models.User, models.UserSession]:
        login = (login or "").strip()
        if settings.APP_ENV != "testing" and not rate_limiter.allow(f"login:{ip}:{login.lower()}", 10, 600):
            raise AuthError("too_many_attempts")
        q = self.db.query(models.User).filter(
            or_(models.User.email == login.lower(), models.User.username == login)
        )
        user = q.first()
        if not user or not verify_password(password, user.password_hash):
            raise AuthError("invalid_credentials")
        if user.is_banned:
            raise AuthError("account_banned")
        if not user.is_active:
            raise AuthError("account_disabled")
        return user, self.create_session(user, ip=ip, ua=ua)

    def create_session(self, user: models.User, ip: str = "", ua: str = "") -> models.UserSession:
        expires = dt.datetime.utcnow() + dt.timedelta(hours=settings.SESSION_TTL_HOURS)
        sess = models.UserSession(
            user_id=user.id, token=new_token(), csrf_token=new_token(24),
            user_agent=ua[:500], ip=ip,
            expires_at=expires,
        )
        self.db.add(sess)
        self.db.commit()
        return sess

    def get_session_user(self, token: str) -> tuple[models.User | None, models.UserSession | None]:
        from sqlalchemy.orm import selectinload
        if not token:
            return None, None
        sess = self.db.query(models.UserSession).filter_by(token=token).first()
        if not sess:
            return None, None
        if sess.expires_at < dt.datetime.utcnow():
            self.db.delete(sess)
            self.db.commit()
            return None, None
        user = self.db.query(models.User).options(
            selectinload(models.User.roles).selectinload(models.UserRole.role)
        ).filter_by(id=sess.user_id).first()
        if not user or user.is_banned or not user.is_active:
            return None, None
        # touch relationships so the object stays usable after expunge/close
        for ur in user.roles:
            _ = ur.role.name if ur.role else None
        return user, sess

    def logout(self, token: str) -> None:
        sess = self.db.query(models.UserSession).filter_by(token=token).first()
        if sess:
            self.db.delete(sess)
            self.db.commit()

    def rotate_session(self, sess: models.UserSession) -> models.UserSession:
        sess.token = new_token()
        sess.csrf_token = new_token(24)
        self.db.commit()
        return sess

    # ----- password reset -----
    def forgot_password(self, email: str) -> str | None:
        """Returns reset token (emailed in production; returned for dev/testing)."""
        email = (email or "").strip().lower()
        user = self.db.query(models.User).filter_by(email=email).first()
        if not user:
            return None  # do not reveal existence
        if not rate_limiter.allow(f"forgot:{email}", 5, 3600):
            raise AuthError("too_many_attempts")
        user.reset_token = new_token(24)
        user.reset_expires = dt.datetime.utcnow() + dt.timedelta(hours=2)
        self.db.commit()
        log.info("password reset requested user_id=%s", user.id)
        return user.reset_token

    def reset_password(self, token: str, password: str, password_confirm: str) -> models.User:
        user = self.db.query(models.User).filter_by(reset_token=token).first()
        if not user or not user.reset_expires or user.reset_expires < dt.datetime.utcnow():
            raise AuthError("invalid_reset_token")
        if password != password_confirm:
            raise AuthError("password_mismatch")
        ok, key = validate_password_strength(password)
        if not ok:
            raise AuthError(key)
        user.password_hash = hash_password(password)
        user.reset_token = ""
        user.reset_expires = None
        # invalidate all sessions
        self.db.query(models.UserSession).filter_by(user_id=user.id).delete()
        self.db.commit()
        return user

    def verify_email(self, token: str) -> bool:
        user = self.db.query(models.User).filter_by(email_verify_token=token).first()
        if not user:
            return False
        user.email_verified = True
        user.email_verify_token = ""
        self.db.commit()
        return True
