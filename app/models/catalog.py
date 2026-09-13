"""Games, categories, fields, products, variants."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class GameCategory(Base, TimestampMixin):
    __tablename__ = "game_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    icon: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Game(Base, TimestampMixin):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    logo: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    cover: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    banner: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("game_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seo_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    seo_description: Mapped[str] = mapped_column(String(512), default="", nullable=False)

    fields: Mapped[list["GameField"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class GameField(Base):
    __tablename__ = "game_fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False)  # player_id, region, nickname...
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    field_type: Mapped[str] = mapped_column(String(16), default="text", nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    placeholder: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game: Mapped["Game"] = relationship(back_populates="fields")


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_game_status", "game_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int | None] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="topup", nullable=False)  # topup/currency/giftcard/digital
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier_product_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    supplier_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    customer_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    old_price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    markup_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    payment_fee_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    platform_fee_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    commission_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    minimum_margin_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    maximum_discount_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)
    override_loss_protection: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    stock_status: Mapped[str] = mapped_column(String(16), default="in_stock", nullable=False)
    image: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    popular: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    game: Mapped["Game | None"] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sku: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    price_delta: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    supplier_product_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    product: Mapped["Product"] = relationship(back_populates="variants")
