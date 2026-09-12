"""Supplier engine models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import SupplierAttemptOutcome, SupplierOrderStatus, SupplierStatus


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    provider_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="http_json")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SupplierStatus.INACTIVE.value, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)  # lower = preferred
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Non-secret config (endpoint templates, field mapping). Secrets live in encrypted_config.
    config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Fernet-encrypted blob: {"base_url": ..., "api_key": ..., "api_secret": ...} — never rendered in UI.
    encrypted_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(16, 2), nullable=True)
    balance_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    balance_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success_rate_30d: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    products: Mapped[List[SupplierProduct]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class SupplierProduct(Base):
    """Mapping: VYRON ProductVariant <-> supplier's external product."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "variant_id", name="uq_supplier_variant"),
        Index("ix_supplier_product_variant_active", "variant_id", "available"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    supplier_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_product_id: Mapped[str] = mapped_column(String(120), nullable=False)
    supplier_cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stock: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    supplier: Mapped[Supplier] = relationship(back_populates="products")


class SupplierOrder(Base):
    """One delivery attempt-window per order item per supplier.

    `idempotency_key` is unique — the same order item can NEVER be submitted
    twice to the same supplier with the same key even under retries/timeouts.
    """

    __tablename__ = "supplier_orders"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_supplier_order_idempotency"),
        Index("ix_supplier_orders_status_reconcile", "status", "reconcile_after"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(GUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    order_item_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("order_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_id: Mapped[str] = mapped_column(GUID, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    external_order_id: Mapped[Optional[str]] = mapped_column(String(190), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(140), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=SupplierOrderStatus.PENDING.value, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    recipient_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # playerId etc. (validated)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    reconcile_after: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    order_item: Mapped[OrderItem] = relationship("OrderItem", back_populates="supplier_orders")  # noqa: F821
    supplier: Mapped[Supplier] = relationship()
    attempts_log: Mapped[List[SupplierOrderAttempt]] = relationship(
        back_populates="supplier_order", cascade="all, delete-orphan", order_by="SupplierOrderAttempt.attempt_no"
    )


class SupplierOrderAttempt(Base):
    __tablename__ = "supplier_order_attempts"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    supplier_order_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("supplier_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    action: Mapped[str] = mapped_column(String(24), nullable=False, default="CREATE")  # CREATE|STATUS|CANCEL|REFUND|VALIDATE
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default=SupplierAttemptOutcome.UNKNOWN.value)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    request_ref: Mapped[Optional[str]] = mapped_column(String(190), nullable=True)
    response_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)

    supplier_order: Mapped[SupplierOrder] = relationship(back_populates="attempts_log")
