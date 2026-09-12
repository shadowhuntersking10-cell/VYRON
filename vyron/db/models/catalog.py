"""Catalog models: games, products, variants."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import GameStatus, ProductType


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=GameStatus.ACTIVE.value, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    # Default dynamic top-up requirements, e.g.
    # [{"name":"playerId","label":"Player ID","type":"text","required":true,"pattern":"^\\d{6,12}$"}]
    required_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    products: Mapped[List[Product]] = relationship(back_populates="game")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_game_active_sort", "game_id", "active", "sort_order"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    game_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("games.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[str] = mapped_column(String(24), nullable=False, default=ProductType.TOPUP.value, index=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Product-level override of game.required_fields (dynamic per-game/per-product inputs)
    required_fields: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    game: Mapped[Optional[Game]] = relationship(back_populates="products")
    variants: Mapped[List[ProductVariant]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductVariant.sort_order"
    )

    @property
    def effective_required_fields(self) -> List[dict]:
        fields = self.required_fields
        if fields is None and self.game is not None:
            fields = self.game.required_fields
        if not fields:
            return []
        if isinstance(fields, dict):
            fields = fields.get("fields", [])
        return [f for f in fields if isinstance(f, dict)]


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_variant_product_name"),
        Index("ix_variant_external", "external_product_id"),
    )

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(
        GUID, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    external_product_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=Decimal("0.00"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)  # -1 = unlimited
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    product: Mapped[Product] = relationship(back_populates="variants")

    @property
    def margin(self) -> Decimal:
        """Gross margin per unit (selling - supplier cost). Never exposed to customers."""
        return Decimal(self.selling_price) - Decimal(self.cost_price)
