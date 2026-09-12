"""Payment, webhook, transaction ledger, refund and revenue accounting models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import PaymentPurpose, PaymentStatus, RefundStatus


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_reference"),
        Index("ix_payments_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    order_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Reverse references (children carry the real FKs to payments; these are plain
    # indexed columns to avoid circular foreign keys — integrity enforced in services).
    donation_id: Mapped[Optional[str]] = mapped_column(GUID, nullable=True, index=True)
    seller_order_id: Mapped[Optional[str]] = mapped_column(GUID, nullable=True, index=True)
    listing_promotion_id: Mapped[Optional[str]] = mapped_column(GUID, nullable=True, index=True)
    seller_subscription_id: Mapped[Optional[str]] = mapped_column(GUID, nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    purpose: Mapped[str] = mapped_column(String(24), nullable=False, default=PaymentPurpose.ORDER.value, index=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    status: Mapped[str] = mapped_column(String(28), nullable=False, default=PaymentStatus.PENDING.value, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    processing_fee: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    refunded_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))

    checkout_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    # Internal idempotency token sent to the provider so retries never double-charge.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    paid_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    order: Mapped[Optional[Order]] = relationship("Order", back_populates="payments")  # noqa: F821


class PaymentWebhook(Base):
    """Every inbound webhook event. Unique (provider, event_id) => replay/duplicate protection."""

    __tablename__ = "payment_webhooks"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(190), nullable=False, index=True)
    event_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class Transaction(Base):
    """Immutable money-movement ledger (audit trail for every financial event)."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transaction_idempotency"),
        Index("ix_transactions_type_created", "type", "created_at"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)  # signed
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    payment_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    seller_profile_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("seller_profiles.id", ondelete="SET NULL"), nullable=True
    )
    payout_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("payout_requests.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    payment_id: Mapped[str] = mapped_column(GUID, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RefundStatus.PENDING.value, index=True)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    requested_by_user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    processed_by_user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    payment: Mapped[Payment] = relationship()


class RevenueLedgerEntry(Base):
    """Immutable platform-revenue ledger backing /admin/revenue.

    Rows are append-only; corrections are made with compensating entries.
    Only verified payments & completed business events may write here.
    """

    __tablename__ = "revenue_ledger"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_revenue_ledger_idempotency"),
        Index("ix_revenue_stream_created", "stream", "created_at"),
        Index("ix_revenue_game_created", "game_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    stream: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # RevenueStream
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)       # always positive magnitude
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    donation_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("donations.id", ondelete="SET NULL"), nullable=True)
    seller_order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("seller_orders.id", ondelete="SET NULL"), nullable=True)
    payout_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("payout_requests.id", ondelete="SET NULL"), nullable=True)
    product_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    game_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("games.id", ondelete="SET NULL"), nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
