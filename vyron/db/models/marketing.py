"""Coupons & promotions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import CouponType


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default=CouponType.PERCENTAGE.value)
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)          # pct (0-100) or fixed amount
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    max_discount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)  # cap for percentage
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # guarded with row locks
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    min_order_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    product_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)        # restrict to products
    game_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)           # restrict to games
    user_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)           # restrict to specific users
    starts_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (UniqueConstraint("coupon_id", "order_id", name="uq_redemption_coupon_order"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    coupon_id: Mapped[str] = mapped_column(GUID, ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    discount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    coupon: Mapped[Coupon] = relationship()


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="BANNER")  # BANNER|CAMPAIGN|SALE
    target_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    badge_text: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)
