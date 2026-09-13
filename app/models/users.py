"""users, user_sessions, telegram_users, admins."""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    USER = "USER"
    SELLER = "SELLER"
    ADMIN = "ADMIN"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(8), default="uz", nullable=False)
    theme: Mapped[str] = mapped_column(String(16), default="system", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    telegram_accounts: Mapped[list["TelegramUser"]] = relationship(back_populates="user")

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class TelegramUser(Base, TimestampMixin):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_auth_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User | None] = relationship(back_populates="telegram_accounts")


class Admin(Base, TimestampMixin):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    permissions: Mapped[str] = mapped_column(Text, default="*", nullable=False)  # JSON list or "*"
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
