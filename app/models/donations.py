"""Donation profiles, presets, donations."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class DonationProfile(Base, TimestampMixin):
    __tablename__ = "donation_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    avatar: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    cover: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    goal_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    raised_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DonationPreset(Base):
    __tablename__ = "donation_presets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Donation(Base, TimestampMixin):
    __tablename__ = "donations"
    __table_args__ = (Index("ix_donations_profile", "profile_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("donation_profiles.id", ondelete="CASCADE"), nullable=False
    )
    donor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    message: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    donor_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
