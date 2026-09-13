"""orders, order_items, payments, payment_transactions, refunds, coupons,
promotions, wallets, wallet_transactions, revenue_ledger."""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SUPPLIER_PROCESSING = "SUPPLIER_PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    SUPPLIER_NOT_CONFIGURED = "SUPPLIER_NOT_CONFIGURED"


class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.PENDING_PAYMENT, nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)

    subtotal: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    service_fee: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    platform_fee: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    # FX snapshot (server-side conversion; base books kept in fx_base_currency)
    fx_base_currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    fx_rate: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    fx_quoted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    coupon_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Player/game fields submitted at checkout: {"player_id": "...", "server": "..."}
    customer_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timeline: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_orders_user_status", "user_id", "status"),)


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="product", nullable=False)  # product|marketplace|donation
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    supplier_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # payme|click|stripe|wallet
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.CREATED, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    checkout_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_init: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paid_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order | None] = relationship(back_populates="payments")
    transactions: Mapped[list["PaymentTransaction"]] = relationship(back_populates="payment", cascade="all, delete-orphan")


class PaymentTransaction(Base, TimestampMixin):
    __tablename__ = "payment_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # init|webhook|verify|refund|capture
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signature_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    payment: Mapped[Payment] = relationship(back_populates="transactions")


class Refund(Base, TimestampMixin):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED", nullable=False, index=True)
    processed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Coupon(Base, TimestampMixin):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="percent", nullable=False)  # percent|fixed
    value: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    min_order: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(nullable=True)
    per_user_limit: Mapped[int] = mapped_column(default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(default=0, nullable=False)
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class CouponUsage(Base):
    __tablename__ = "coupon_usages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Promotion(Base, TimestampMixin):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    coupon_id: Mapped[int | None] = mapped_column(ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True)
    starts_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)


class WalletTransaction(Base, TimestampMixin):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # topup|spend|refund|payout|commission
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    balance_after: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class RevenueLedger(Base, TimestampMixin):
    __tablename__ = "revenue_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stream: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # topup_markup|marketplace_commission|donation_fee|service_fee|promo
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    gross: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    supplier_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    processing_fee: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    seller_payout: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    net: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_revenue_stream_created", "stream", "created_at"),)
