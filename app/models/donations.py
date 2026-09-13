"""donation_profiles, donation_presets, donations."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DonationProfile(Base, TimestampMixin):
    __tablename__ = "donation_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    goal_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    goal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    current_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    donations: Mapped[list["Donation"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class DonationPreset(Base, TimestampMixin):
    """Admin-configurable donation preset amounts per currency."""

    __tablename__ = "donation_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    __table_args__ = (Index("ix_donation_presets_unique", "currency", "amount", unique=True),)


class Donation(Base, TimestampMixin):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("donation_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)  # pending|paid|failed

    profile: Mapped[DonationProfile] = relationship(back_populates="donations")

    __table_args__ = (Index("ix_donations_profile_status", "profile_id", "status"),)
