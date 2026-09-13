"""Suppliers, supplier products mapping, supplier orders."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    adapter: Mapped[str] = mapped_column(String(64), default="generic_http", nullable=False)
    api_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    api_key: Mapped[str] = mapped_column(String(512), default="", nullable=False)  # never expose via API
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    auto_price_update: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_error: Mapped[str] = mapped_column(String(512), default="", nullable=False)


class SupplierProduct(Base, TimestampMixin):
    __tablename__ = "supplier_products"
    __table_args__ = (Index("ix_supprod_supplier_ext", "supplier_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SupplierOrder(Base, TimestampMixin):
    __tablename__ = "supplier_orders"
    __table_args__ = (Index("ix_suporder_ref", "reference", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    reference: Mapped[str] = mapped_column(String(128), nullable=False)  # unique idempotency ref
    external_order_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    payload: Mapped[str] = mapped_column(Text, default="", nullable=False)  # JSON sent
    response: Mapped[str] = mapped_column(Text, default="", nullable=False)  # JSON received
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str] = mapped_column(String(512), default="", nullable=False)
