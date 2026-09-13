"""Marketplace: sellers, listings, balances, payouts."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class MarketplaceCategory(Base, TimestampMixin):
    __tablename__ = "marketplace_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    icon: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    commission_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)  # 0 = use global
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    shop_name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    logo: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    banner: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    commission_percent: Mapped[float] = mapped_column(Numeric(8, 4), default=0, nullable=False)  # 0 = use category/global
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class MarketplaceListing(Base, TimestampMixin):
    __tablename__ = "marketplace_listings"
    __table_args__ = (Index("ix_listing_cat_status", "category_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("marketplace_categories.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0, nullable=False)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    images: Mapped[list["MarketplaceListingImage"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )


class MarketplaceListingImage(Base):
    __tablename__ = "marketplace_listing_images"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    listing: Mapped["MarketplaceListing"] = relationship(back_populates="images")


class SellerBalance(Base, TimestampMixin):
    __tablename__ = "seller_balances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(
        ForeignKey("sellers.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    available: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    pending: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    lifetime_earned: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)


class SellerPayout(Base, TimestampMixin):
    __tablename__ = "seller_payouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    method: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    details: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
