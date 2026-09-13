"""sellers, seller_balances, seller_payouts, marketplace_listings."""
from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PayoutStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    shop_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(default=0, nullable=False)
    sales_count: Mapped[int] = mapped_column(default=0, nullable=False)
    commission_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)  # override
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    listings: Mapped[list["MarketplaceListing"]] = relationship(back_populates="seller", cascade="all, delete-orphan")


class SellerBalance(Base, TimestampMixin):
    __tablename__ = "seller_balances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), unique=True, nullable=False)
    available: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    pending: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    lifetime_earned: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)


class SellerPayout(Base, TimestampMixin):
    __tablename__ = "seller_payouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    status: Mapped[PayoutStatus] = mapped_column(Enum(PayoutStatus), default=PayoutStatus.REQUESTED, nullable=False, index=True)
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class MarketplaceListing(Base, TimestampMixin):
    __tablename__ = "marketplace_listings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="other", nullable=False, index=True)
    delivery_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    stock: Mapped[int] = mapped_column(default=-1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)  # active|paused|sold|deleted
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    views: Mapped[int] = mapped_column(default=0, nullable=False)

    seller: Mapped[Seller] = relationship(back_populates="listings")

    __table_args__ = (Index("ix_listings_status_category", "status", "category"),)
