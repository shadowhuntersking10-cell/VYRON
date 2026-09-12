"""Seller marketplace models: profiles, listings, orders, balances, payouts, promotions, subscriptions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import (
    ListingDeliveryType,
    ListingStatus,
    PayoutStatus,
    PromotionKind,
    SellerOrderStatus,
    SellerStatus,
    SellerVerificationStatus,
    SubscriptionStatus,
)


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0.00"))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SellerVerificationStatus.UNVERIFIED.value, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SellerStatus.ACTIVE.value, index=True)
    commission_override_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship("User", lazy="joined")  # noqa: F821
    listings: Mapped[List[SellerListing]] = relationship(back_populates="seller")
    balance: Mapped[Optional[SellerBalance]] = relationship(back_populates="seller", uselist=False)


class SellerListing(Base):
    __tablename__ = "seller_listings"
    __table_args__ = (Index("ix_listings_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    game_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    delivery_type: Mapped[str] = mapped_column(String(16), nullable=False, default=ListingDeliveryType.MANUAL.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ListingStatus.DRAFT.value, index=True)
    images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    # Sensitive delivery payload (only for legitimate, permitted digital deliveries).
    # Fernet-encrypted at rest; revealed only to the buyer AFTER order completion.
    sensitive_delivery_data_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    seller: Mapped[SellerProfile] = relationship(back_populates="listings")
    game: Mapped[Optional[Game]] = relationship("Game", lazy="joined")  # noqa: F821


class SellerOrder(Base):
    """A marketplace purchase: customer pays platform, platform takes commission, seller gets earnings."""

    __tablename__ = "seller_orders"
    __table_args__ = (Index("ix_seller_orders_seller_created", "seller_id", "created_at"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)  # VYM-2026-000001
    listing_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    buyer_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    commission_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    seller_earning: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=SellerOrderStatus.PENDING_PAYMENT.value, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    delivery_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    listing: Mapped[SellerListing] = relationship(lazy="joined")
    buyer: Mapped[User] = relationship("User", foreign_keys=[buyer_id], lazy="joined")  # noqa: F821


class SellerBalance(Base):
    """pending -> available (after holding period) -> paid (lifetime payouts)."""

    __tablename__ = "seller_balances"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    pending: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    available: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    reserved: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))  # payout in-flight
    lifetime_earnings: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    lifetime_paid: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    seller: Mapped[SellerProfile] = relationship(back_populates="balance")


class SellerBalanceTransaction(Base):
    __tablename__ = "seller_balance_transactions"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_seller_balance_tx_idempotency"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # BalanceTxType
    pending_delta: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    available_delta: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # SELLER_ORDER|PAYOUT|ADMIN
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    available_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)  # hold release time
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)


class PayoutRequest(Base):
    __tablename__ = "payout_requests"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    method: Mapped[str] = mapped_column(String(24), nullable=False, default="CARD")  # CARD|UZCARD|HUMO|PAYME|BANK
    details_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # encrypted payout destination
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PayoutStatus.PENDING.value, index=True)
    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)  # external transfer ref
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ListingPromotion(Base):
    """Paid listing promotion (revenue stream #4). Admin controls pricing via PlatformSetting."""

    __tablename__ = "listing_promotions"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    listing_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default=PromotionKind.FEATURED.value)
    price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", index=True)  # PENDING|ACTIVE|EXPIRED|CANCELLED
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    starts_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class SellerSubscriptionPlan(Base):
    """Seller premium feature plans (revenue stream #5). Optional — never forced."""

    __tablename__ = "seller_subscription_plans"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    features: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)


class SellerSubscription(Base):
    __tablename__ = "seller_subscriptions"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    seller_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("seller_subscription_plans.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SubscriptionStatus.ACTIVE.value, index=True)
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
