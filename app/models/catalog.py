"""games, game_categories, game_fields, products, product_variants,
suppliers, supplier_products, supplier_orders."""
from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class GameCategory(Base, TimestampMixin):
    __tablename__ = "game_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name_uz: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Game(Base, TimestampMixin):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("game_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Required player fields config: [{"key":"player_id","label":{...},"required":true},...]
    # Source of truth: game_fields rows when present, else this JSON.
    fields_schema: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    fields: Mapped[list["GameField"]] = relationship(back_populates="game", cascade="all, delete-orphan")

    __table_args__ = (Index("ix_games_active_featured", "is_active", "is_featured"),)


class GameField(Base, TimestampMixin):
    """Required player fields per game (structured version of fields_schema)."""

    __tablename__ = "game_fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label_uz: Mapped[str] = mapped_column(String(128), nullable=False)
    label_en: Mapped[str] = mapped_column(String(128), nullable=False)
    label_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    game: Mapped[Game] = relationship(back_populates="fields")

    __table_args__ = (Index("ix_game_fields_unique", "game_id", "key", unique=True),)


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    supplier_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)  # NEVER exposed to clients
    selling_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    # ---- pricing engine inputs (all server-side) ----
    payment_fee_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    payment_fixed_fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    platform_margin_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    platform_fixed_fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    minimum_margin_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    maximum_discount_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    loss_leader_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_type: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)  # auto|manual|code
    stock: Mapped[int] = mapped_column(default=-1, nullable=False)  # -1 = unlimited
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    game: Mapped[Game] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    selling_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    payment_fee_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    payment_fixed_fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    platform_margin_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    platform_fixed_fee: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    minimum_margin_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    maximum_discount_percent: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    loss_leader_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stock: Mapped[int] = mapped_column(default=-1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[Product] = relationship(back_populates="variants")


class SupplierStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)  # manual|generic|...
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    api_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Credentials live in ENV; this holds non-secret config + a flag.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    balance_currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    status: Mapped[SupplierStatus] = mapped_column(Enum(SupplierStatus), default=SupplierStatus.ACTIVE, nullable=False)


class SupplierProduct(Base, TimestampMixin):
    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_supplier_products_unique", "supplier_id", "external_id", unique=True),)


class SupplierOrder(Base, TimestampMixin):
    __tablename__ = "supplier_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
