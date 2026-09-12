"""Telegram service — Mini App auth (initData), account linking, admin gate.

The Mini App session is established ONLY after cryptographic validation of
Telegram initData on the server. Admin exposure is decided server-side from
ADMIN_TELEGRAM_IDS and/or the linked account's role — never from client claims.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.models import TelegramConnection, User
from vyron.enums import ADMIN_ROLES, UserRole, UserStatus
from vyron.errors import ConflictError, NotFoundError
from vyron.logging import get_logger
from vyron.security.hashing import hash_password
from vyron.security.telegram_auth import TelegramUser, is_telegram_admin_id, validate_init_data
from vyron.services import auth_service, notification_service

log = get_logger("vyron.telegram")

TELEGRAM_EMAIL_DOMAIN = "tg.vyron.internal"


def _provision_telegram_user(db: DbSession, tg_user: TelegramUser) -> User:
    """Create a real VYRON account bound to a verified Telegram identity."""
    base_username = f"tg_{tg_user.id}"
    username = base_username
    suffix = 0
    while db.query(User).filter(User.username == username).first():
        suffix += 1
        username = f"{base_username}_{suffix}"[:30]
    email = f"telegram_{tg_user.id}@{TELEGRAM_EMAIL_DOMAIN}"
    if db.query(User).filter(User.email == email).first():
        raise ConflictError("Telegram identity already provisioned.", code="TELEGRAM_CONFLICT")

    locale = "ru" if (tg_user.language_code or "").lower().startswith("ru") else "uz"
    user = User(
        name=(tg_user.first_name or username)[:120],
        username=username,
        email=email,
        # Unusable random password — account authenticates via Telegram or via
        # password reset flow once the user attaches a real email.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=UserRole.USER.value,
        status=UserStatus.ACTIVE.value,
        email_verified=True,  # identity verified by Telegram itself
        locale=locale,
    )
    db.add(user)
    db.flush()
    return user


def _upsert_connection(db: DbSession, user: User, tg_user: TelegramUser) -> TelegramConnection:
    connection = db.query(TelegramConnection).filter(TelegramConnection.telegram_id == tg_user.id).first()
    if connection is None:
        connection = TelegramConnection(
            user_id=user.id,
            telegram_id=tg_user.id,
            telegram_username=tg_user.username or None,
            first_name=tg_user.first_name or None,
            language_code=tg_user.language_code or None,
            is_premium=tg_user.is_premium,
        )
        db.add(connection)
    else:
        connection.user_id = user.id
        connection.telegram_username = tg_user.username or connection.telegram_username
        connection.first_name = tg_user.first_name or connection.first_name
        connection.is_premium = tg_user.is_premium
    db.flush()
    return connection


def is_admin_context(db: DbSession, user: Optional[User], telegram_id: int) -> bool:
    """Server-side admin decision for Telegram contexts."""
    if is_telegram_admin_id(telegram_id):
        return True
    if user is not None and UserRole(user.role) in ADMIN_ROLES:
        return True
    return False


def authenticate_miniapp(db: DbSession, init_data: str) -> Dict[str, Any]:
    """Validate initData and return {user, is_admin, is_new} for session issuance."""
    parsed = validate_init_data(init_data)
    if parsed.user is None:
        from vyron.errors import AuthError

        raise AuthError("initData does not contain a user.", code="TELEGRAM_INIT_DATA_INVALID")
    tg_user = parsed.user

    connection = db.query(TelegramConnection).filter(TelegramConnection.telegram_id == tg_user.id).first()
    is_new = False
    if connection is not None:
        user = db.get(User, connection.user_id)
        if user is None or user.status != UserStatus.ACTIVE.value:
            from vyron.errors import AccountDisabledError

            raise AccountDisabledError()
        # refresh profile bits
        connection.telegram_username = tg_user.username or connection.telegram_username
        connection.is_premium = tg_user.is_premium
        db.commit()
    else:
        user = _provision_telegram_user(db, tg_user)
        _upsert_connection(db, user, tg_user)
        is_new = True
        db.commit()
        notification_service.notify_event(db, user, "welcome", {"name": user.name})

    start_param = parsed.start_param
    linked_via_token = False
    if start_param and not connection:
        # /start <link-token> flow launched inside the Mini App
        try:
            target_user = auth_service.consume_telegram_link_token(db, start_param)
            _upsert_connection(db, target_user, tg_user)
            db.commit()
            user = target_user
            linked_via_token = True
            notification_service.notify_event(db, user, "telegram_linked")
        except Exception as exc:
            db.rollback()
            log.warning(f"miniapp start_param link failed: {exc}")

    return {
        "user": user,
        "is_admin": is_admin_context(db, user, tg_user.id),
        "is_new": is_new,
        "linked_via_token": linked_via_token,
        "telegram_user": tg_user,
    }


def link_account(db: DbSession, user: User, tg_user: TelegramUser) -> TelegramConnection:
    existing = db.query(TelegramConnection).filter(TelegramConnection.telegram_id == tg_user.id).first()
    if existing and existing.user_id != user.id:
        raise ConflictError("This Telegram account is already linked to another user.", code="TELEGRAM_ALREADY_LINKED")
    own = db.query(TelegramConnection).filter(TelegramConnection.user_id == user.id).first()
    if own:
        return own
    connection = _upsert_connection(db, user, tg_user)
    db.commit()
    notification_service.notify_event(db, user, "telegram_linked")
    return connection


def unlink_account(db: DbSession, user: User) -> None:
    deleted = db.query(TelegramConnection).filter(TelegramConnection.user_id == user.id).delete()
    db.commit()
    if not deleted:
        raise NotFoundError("No Telegram connection found.")


def get_link_token(db: DbSession, user: User) -> Dict[str, Any]:
    token = auth_service.create_telegram_link_token(db, user)
    bot_username = ""
    if settings.telegram_bot_token:
        bot_username = ""  # resolved by the bot at runtime via getMe when needed
    return {
        "token": token,
        "instruction": f"Open the VYRON bot in Telegram and send: /start {token}",
        "expires_in_minutes": 10,
        "bot_username": bot_username,
    }


def connection_for_user(db: DbSession, user: User) -> Optional[TelegramConnection]:
    return db.query(TelegramConnection).filter(TelegramConnection.user_id == user.id).first()


def miniapp_admin_payload(db: DbSession, user: User) -> Dict[str, Any]:
    connection = connection_for_user(db, user)
    telegram_id = connection.telegram_id if connection else 0
    return {"is_admin": is_admin_context(db, user, telegram_id), "role": user.role}
