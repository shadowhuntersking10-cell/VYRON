"""Authentication service — registration, login, email verification, password reset.

Real security properties:
- Argon2id password hashing (never plaintext, never returned)
- one-time expiring tokens (stored hashed) for verification & reset
- user enumeration prevented on forgot-password
- all sensitive flows rate limited at the API layer
- every auth event audited
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.base import utcnow
from vyron.db.models import LoginAttempt, PasswordResetToken, TelegramLinkToken, User, VerificationToken
from vyron.enums import UserRole, UserStatus
from vyron.errors import AuthError, ConflictError, InvalidCredentialsError, NotFoundError, ValidationError
from vyron.logging import get_logger
from vyron.security.hashing import generate_token, hash_password, hash_token, verify_password
from vyron.services import audit_service, notification_service

log = get_logger("vyron.auth")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class AuthResult:
    user: User
    token_plain: Optional[str] = None  # for verification/reset emails


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.", code="PASSWORD_TOO_SHORT")
    if len(password) > 200:
        raise ValidationError("Password is too long.", code="PASSWORD_TOO_LONG")


def register_user(
    db: DbSession,
    *,
    name: str,
    username: str,
    email: str,
    password: str,
    confirm_password: str,
    phone: Optional[str] = None,
    locale: str = "uz",
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> User:
    name = (name or "").strip()
    username = (username or "").strip().lower()
    email = (email or "").strip().lower()

    if not name or len(name) < 2:
        raise ValidationError("Name is required.", code="NAME_REQUIRED")
    if not USERNAME_RE.match(username):
        raise ValidationError("Username must be 3-30 characters (letters, digits, underscore).", code="USERNAME_INVALID")
    if not EMAIL_RE.match(email):
        raise ValidationError("Email is invalid.", code="EMAIL_INVALID")
    if password != confirm_password:
        raise ValidationError("Passwords do not match.", code="PASSWORDS_MISMATCH")
    _validate_password(password)

    if db.query(User).filter(User.username == username).first():
        raise ConflictError("This username is already taken.", code="USERNAME_TAKEN")
    if db.query(User).filter(User.email == email).first():
        raise ConflictError("This email is already registered.", code="EMAIL_TAKEN")

    user = User(
        name=name[:120],
        username=username,
        email=email,
        phone=(phone or "").strip()[:32] or None,
        password_hash=hash_password(password),
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
        locale=locale if locale in {"uz", "en", "ru"} else "uz",
    )
    db.add(user)
    db.flush()

    token_plain = _create_verification_token(db, user)
    audit_service.record_audit(
        db, "user.registered", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id,
        ip_address=ip_address, user_agent=user_agent, commit=False,
    )
    notification_service.notify_event(db, user, "welcome", {"name": user.name}, commit=False)
    notification_service.queue_email(
        db,
        to_email=user.email,
        subject="Verify your VYRON email",
        body_text=(
            f"Welcome to VYRON, {user.name}!\n\n"
            f"Verify your email: {settings.public_base_url.rstrip('/')}/verify-email?token={token_plain}\n\n"
            "This link expires in 48 hours."
        ),
        user_id=user.id,
        idempotency_key=f"verify:{user.id}:{token_plain[:12]}",
        commit=False,
    )
    db.commit()
    log.info("user registered", username=username)
    return user


def _create_verification_token(db: DbSession, user: User) -> str:
    plain = generate_token(32)
    db.add(
        VerificationToken(
            user_id=user.id,
            token_hash=hash_token(plain),
            purpose="EMAIL_VERIFY",
            expires_at=VerificationToken.ttl(48),
        )
    )
    db.flush()
    return plain


def verify_email(db: DbSession, token_plain: str) -> User:
    token = (
        db.query(VerificationToken)
        .filter(
            VerificationToken.token_hash == hash_token(token_plain),
            VerificationToken.purpose == "EMAIL_VERIFY",
        )
        .first()
    )
    if token is None or token.used_at is not None or token.expires_at < utcnow():
        raise AuthError("This verification link is invalid or has expired.", code="VERIFY_INVALID")
    user = db.get(User, token.user_id)
    if user is None:
        raise NotFoundError("User not found.")
    token.used_at = utcnow()
    user.email_verified = True
    db.commit()
    notification_service.notify_event(db, user, "email_verified")
    audit_service.record_audit(db, "user.email_verified", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id)
    return user


def resend_verification(db: DbSession, user: User) -> str:
    if user.email_verified:
        raise ValidationError("Email is already verified.", code="ALREADY_VERIFIED")
    token_plain = _create_verification_token(db, user)
    notification_service.queue_email(
        db,
        to_email=user.email,
        subject="Verify your VYRON email",
        body_text=f"Verify your email: {settings.public_base_url.rstrip('/')}/verify-email?token={token_plain}\n\nThis link expires in 48 hours.",
        user_id=user.id,
        idempotency_key=f"verify:{user.id}:{token_plain[:12]}",
    )
    return token_plain


def login_user(
    db: DbSession,
    *,
    email: str,
    password: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> User:
    email = (email or "").strip().lower()
    user = db.query(User).filter(User.email == email).first()

    attempt = LoginAttempt(email=email[:255], ip_address=ip_address, user_agent=(user_agent or "")[:400] or None)
    if user is None or not verify_password(password, user.password_hash):
        attempt.success = False
        attempt.failure_reason = "INVALID_CREDENTIALS"
        attempt.user_id = user.id if user else None
        db.add(attempt)
        db.commit()
        log.warning("failed login", email=email)
        raise InvalidCredentialsError()

    if user.status != UserStatus.ACTIVE.value:
        attempt.success = False
        attempt.failure_reason = "ACCOUNT_DISABLED"
        attempt.user_id = user.id
        db.add(attempt)
        db.commit()
        raise AuthError("This account has been disabled. Contact support.", code="ACCOUNT_DISABLED")

    attempt.success = True
    attempt.user_id = user.id
    db.add(attempt)
    user.last_login_at = utcnow()
    db.commit()
    audit_service.record_audit(db, "user.login", actor_id=user.id, actor_type="USER", actor_role=user.role, entity_type="user", entity_id=user.id, ip_address=ip_address, user_agent=user_agent)
    return user


def forgot_password(db: DbSession, email: str) -> Optional[str]:
    """Returns the reset token ONLY in development (emails it in all envs).
    Response is identical whether or not the account exists (anti-enumeration)."""
    user = db.query(User).filter(User.email == (email or "").strip().lower()).first()
    if user is None:
        return None
    plain = generate_token(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(plain),
            expires_at=PasswordResetToken.ttl(60),
        )
    )
    db.commit()
    notification_service.queue_email(
        db,
        to_email=user.email,
        subject="Reset your VYRON password",
        body_text=(
            f"Hi {user.name},\n\nReset your password: "
            f"{settings.public_base_url.rstrip('/')}/reset-password?token={plain}\n\n"
            "This link expires in 60 minutes. If you didn't request it, ignore this email."
        ),
        user_id=user.id,
        idempotency_key=f"reset:{user.id}:{plain[:12]}",
    )
    audit_service.record_audit(db, "user.password_reset_requested", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id)
    return plain if not settings.is_production else None


def reset_password(db: DbSession, token_plain: str, new_password: str, confirm_password: str) -> User:
    if new_password != confirm_password:
        raise ValidationError("Passwords do not match.", code="PASSWORDS_MISMATCH")
    _validate_password(new_password)
    token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == hash_token(token_plain)).first()
    if token is None or token.used_at is not None or token.expires_at < utcnow():
        raise AuthError("This reset link is invalid or has expired.", code="RESET_INVALID")
    user = db.get(User, token.user_id)
    if user is None:
        raise NotFoundError("User not found.")
    token.used_at = utcnow()
    user.password_hash = hash_password(new_password)
    db.commit()
    # Revoke every session (security requirement on password reset).
    from vyron.security.sessions import revoke_all_user_sessions

    revoke_all_user_sessions(db, user.id)
    notification_service.notify_event(db, user, "password_changed")
    audit_service.record_audit(db, "user.password_reset", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id)
    return user


def change_password(db: DbSession, user: User, current_password: str, new_password: str, confirm_password: str) -> User:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("Current password is incorrect.", code="INVALID_CREDENTIALS")
    if new_password != confirm_password:
        raise ValidationError("Passwords do not match.", code="PASSWORDS_MISMATCH")
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    db.commit()
    from vyron.security.sessions import revoke_all_user_sessions

    revoke_all_user_sessions(db, user.id)
    notification_service.notify_event(db, user, "password_changed")
    audit_service.record_audit(db, "user.password_changed", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id)
    return user


def create_telegram_link_token(db: DbSession, user: User) -> str:
    """One-time token (10 min) used via `/start <token>` in the bot."""
    plain = generate_token(24)
    db.add(
        TelegramLinkToken(
            user_id=user.id,
            token_hash=hash_token(plain),
            expires_at=TelegramLinkToken.ttl(10),
        )
    )
    db.commit()
    return plain


def consume_telegram_link_token(db: DbSession, token_plain: str) -> User:
    token = db.query(TelegramLinkToken).filter(TelegramLinkToken.token_hash == hash_token(token_plain)).first()
    if token is None or token.used_at is not None or token.expires_at < utcnow():
        raise AuthError("This link token is invalid, already used, or expired.", code="LINK_TOKEN_INVALID")
    user = db.get(User, token.user_id)
    if user is None:
        raise NotFoundError("User not found.")
    token.used_at = utcnow()
    db.commit()
    return user
