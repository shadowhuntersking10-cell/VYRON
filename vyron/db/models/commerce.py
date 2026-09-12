"""Commerce models: carts, orders, order items, status history, idempotency."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import OrderStatus, RiskLevel


class Cart(Base):
    __tablename__ = "carts"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    coupon_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items: Mapped[List[CartItem]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id", "values_hash", name="uq_cart_item_variant_values"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    cart_id: Mapped[str] = mapped_column(GUID, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required_field_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    values_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant = relationship("ProductVariant", lazy="joined")

    @staticmethod
    def compute_values_hash(values: Optional[dict]) -> str:
        payload = json.dumps(values or {}, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=OrderStatus.CREATED.value, index=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    discount: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    service_fee: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    supplier_cost_total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))

    coupon_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("coupons.id", ondelete="SET NULL"), nullable=True
    )
    payment_provider: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)

    # Client-generated idempotency key protects against double-click duplicate orders.
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)

    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(12), nullable=False, default=RiskLevel.LOW.value)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    paid_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    items: Mapped[List[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.created_at"
    )
    user: Mapped[User] = relationship("User", lazy="joined")  # noqa: F821
    status_history: Mapped[List[OrderStatusHistory]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.created_at"
    )
    payments: Mapped[List[Payment]] = relationship("Payment", back_populates="order")  # noqa: F821


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(GUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    variant_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    # Snapshots — the order must remain exact even if the catalog changes later.
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    variant_name: Mapped[str] = mapped_column(String(160), nullable=False)
    game_name: Mapped[Optional[str]] = mapped_column(String(140), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    required_field_values: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    delivery_state: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="items")
    variant = relationship("ProductVariant", lazy="joined")
    supplier_orders: Mapped[List[SupplierOrder]] = relationship("SupplierOrder", back_populates="order_item")  # noqa: F821


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(GUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="SYSTEM")  # SYSTEM|USER|ADMIN|WEBHOOK
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="status_history")


class OrderSequence(Base):
    """Transaction-safe order number sequence: VYR-<year>-<000001>.

    A single row per year is locked with SELECT ... FOR UPDATE while allocating.
    """

    __tablename__ = "order_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)


class IdempotencyKey(Base):
    """Generic idempotency registry (checkout, refunds, payouts, supplier submits)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("scope", "key_value", name="uq_idempotency_scope_key"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    key_value: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="COMMITTED")
    response_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
