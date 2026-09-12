"""Donation platform models (revenue stream #3: transparent, configurable platform fee)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import DonationStatus


class DonationPage(Base):
    """Public donation page: /donate/<username>."""

    __tablename__ = "donation_pages"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    goal_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship("User", lazy="joined")  # noqa: F821


class Donation(Base):
    """One donation event. Amounts are computed SERVER-SIDE; status only advances
    from a verified provider webhook (never from the frontend)."""

    __tablename__ = "donations"
    __table_args__ = (Index("ix_donations_page_created", "page_id", "created_at"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("donation_pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    donor_user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    donor_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    donor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)          # to recipient
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)    # charged to donor = amount + fee
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DonationStatus.PENDING.value, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    page: Mapped[DonationPage] = relationship(lazy="joined")


class DonationTransaction(Base):
    """Immutable financial leg of a completed donation (records donor, recipient,
    amount, currency, payment, status, message, anonymous flag, timestamp)."""

    __tablename__ = "donation_transactions"
    __table_args__ = (UniqueConstraint("donation_id", name="uq_donation_tx_donation"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    donation_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("donations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    recipient_user_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    donor_user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
