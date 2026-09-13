from __future__ import annotations
import enum
from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from sqlalchemy import (
    String, Integer, BigInteger, Boolean, DateTime, Text, ForeignKey, 
    UniqueConstraint, Index, Enum as SQLEnum, DECIMAL, func, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

# Enums
class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BANNED = "BANNED"
    INACTIVE = "INACTIVE"

class OrderStatus(str, enum.Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SUPPLIER_PROCESSING = "SUPPLIER_PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"

class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class PaymentProvider(str, enum.Enum):
    PAYME = "PAYME"
    CLICK = "CLICK"
    STRIPE = "STRIPE"
    WALLET = "WALLET"
    TELEGRAM_STARS = "TELEGRAM_STARS"
    MANUAL = "MANUAL"

class SupplierOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ListingStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    SOLD = "SOLD"
    ARCHIVED = "ARCHIVED"
    PENDING_REVIEW = "PENDING_REVIEW"

class TicketStatus(str, enum.Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_USER = "WAITING_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

class MediaType(str, enum.Enum):
    GAME_LOGO = "GAME_LOGO"
    GAME_COVER = "GAME_COVER"
    GAME_BANNER = "GAME_BANNER"
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    MARKETPLACE_IMAGE = "MARKETPLACE_IMAGE"
    AVATAR = "AVATAR"
    DONATION_COVER = "DONATION_COVER"
    PROMOTION_BANNER = "PROMOTION_BANNER"
    TICKET_ATTACHMENT = "TICKET_ATTACHMENT"
    OTHER = "OTHER"

class NotificationType(str, enum.Enum):
    ORDER_CREATED = "ORDER_CREATED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    ORDER_PROCESSING = "ORDER_PROCESSING"
    ORDER_COMPLETED = "ORDER_COMPLETED"
    ORDER_FAILED = "ORDER_FAILED"
    REFUND = "REFUND"
    PROMOTION = "PROMOTION"
    SUPPORT_RESPONSE = "SUPPORT_RESPONSE"
    SYSTEM = "SYSTEM"

# Base mixins
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

# Users
class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255))

class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE.value, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(10), default="uz")
    theme: Mapped[str] = mapped_column(String(20), default="system")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    email_verification_token: Mapped[Optional[str]] = mapped_column(String(255))
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255))
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(DateTime)

    sessions: Mapped[List["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    roles: Mapped[List["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    telegram: Mapped[Optional["TelegramUser"]] = relationship(back_populates="user", uselist=False)
    orders: Mapped[List["Order"]] = relationship(back_populates="user")
    wallet: Mapped[Optional["Wallet"]] = relationship(back_populates="user", uselist=False)

class UserRole(Base):
    __tablename__ = "user_roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship()
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),)

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    user: Mapped["User"] = relationship(back_populates="sessions")

class TelegramUser(Base, TimestampMixin):
    __tablename__ = "telegram_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100))
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    language_code: Mapped[Optional[str]] = mapped_column(String(10))
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    user: Mapped[Optional["User"]] = relationship(back_populates="telegram")

# Games
class GameCategory(Base, TimestampMixin):
    __tablename__ = "game_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Game(Base, TimestampMixin):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    short_description: Mapped[Optional[str]] = mapped_column(String(500))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500))
    cover_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("game_categories.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    popular: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    seo_title: Mapped[Optional[str]] = mapped_column(String(255))
    seo_description: Mapped[Optional[str]] = mapped_column(String(500))
    required_fields_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))

    category: Mapped[Optional["GameCategory"]] = relationship()
    products: Mapped[List["Product"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    fields: Mapped[List["GameField"]] = relationship(back_populates="game", cascade="all, delete-orphan")

class GameField(Base, TimestampMixin):
    __tablename__ = "game_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    placeholder: Mapped[Optional[str]] = mapped_column(String(255))
    field_type: Mapped[str] = mapped_column(String(50), default="text")
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_regex: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    game: Mapped["Game"] = relationship(back_populates="fields")
    __table_args__ = (UniqueConstraint("game_id", "field_key", name="uq_game_fields_game_key"),)

# Suppliers
class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    api_url: Mapped[Optional[str]] = mapped_column(String(500))
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    balance: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    config: Mapped[Optional[dict]] = mapped_column(JSON)

class SupplierProduct(Base, TimestampMixin):
    __tablename__ = "supplier_products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_price: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_product_id", name="uq_supplier_products"),)

class SupplierOrder(Base, TimestampMixin):
    __tablename__ = "supplier_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    supplier_order_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    supplier_product_id: Mapped[Optional[str]] = mapped_column(String(255))
    cost_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    status: Mapped[str] = mapped_column(String(30), default=SupplierOrderStatus.PENDING.value)
    request_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

# Products
class Product(Base, TimestampMixin):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    supplier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"))
    supplier_product_id: Mapped[Optional[str]] = mapped_column(String(255))
    supplier_cost: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    customer_price: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    old_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    markup: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    payment_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    commission: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("0.00"))
    minimum_margin: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("5.00"))
    maximum_discount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("20.00"))
    stock_status: Mapped[str] = mapped_column(String(20), default="IN_STOCK")
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)

    game: Mapped["Game"] = relationship(back_populates="products")
    variants: Mapped[List["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan")

class ProductVariant(Base, TimestampMixin):
    __tablename__ = "product_variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    price_modifier: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped["Product"] = relationship(back_populates="variants")

# Orders
class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.PENDING_PAYMENT.value, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    subtotal: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    service_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    payment_provider: Mapped[Optional[str]] = mapped_column(String(50))
    coupon_code: Mapped[Optional[str]] = mapped_column(String(100))
    game_data: Mapped[Optional[dict]] = mapped_column(JSON)  # player id, region, etc
    notes: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[List["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payment: Mapped[Optional["Payment"]] = relationship(back_populates="order", uselist=False)
    supplier_order: Mapped[Optional["SupplierOrder"]] = relationship()

class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    supplier_cost: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    order: Mapped["Order"] = relationship(back_populates="items")

# Payments
class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.CREATED.value, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    provider_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    raw_request: Mapped[Optional[dict]] = mapped_column(JSON)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    order: Mapped["Order"] = relationship(back_populates="payment")
    transactions: Mapped[List["PaymentTransaction"]] = relationship(back_populates="payment", cascade="all, delete-orphan")

class PaymentTransaction(Base, TimestampMixin):
    __tablename__ = "payment_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_response: Mapped[Optional[dict]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    payment: Mapped["Payment"] = relationship(back_populates="transactions")

class Refund(Base, TimestampMixin):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    processed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

# Marketplace
class MarketplaceCategory(Base, TimestampMixin):
    __tablename__ = "marketplace_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500))
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("marketplace_categories.id", ondelete="SET NULL"))
    commission_rate: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), default=Decimal("10.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Seller(Base, TimestampMixin):
    __tablename__ = "sellers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    shop_name: Mapped[str] = mapped_column(String(150), nullable=False)
    shop_slug: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    commission_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    total_sales: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[Decimal] = mapped_column(DECIMAL(3, 2), default=Decimal("0.00"))
    user: Mapped["User"] = relationship()

class MarketplaceListing(Base, TimestampMixin):
    __tablename__ = "marketplace_listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("marketplace_categories.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    old_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    stock: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default=ListingStatus.ACTIVE.value, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[Decimal] = mapped_column(DECIMAL(3, 2), default=Decimal("0.00"))
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    seller: Mapped["Seller"] = relationship()
    images: Mapped[List["MarketplaceListingImage"]] = relationship(back_populates="listing", cascade="all, delete-orphan")

class MarketplaceListingImage(Base, TimestampMixin):
    __tablename__ = "marketplace_listing_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    listing: Mapped["MarketplaceListing"] = relationship(back_populates="images")

class SellerBalance(Base, TimestampMixin):
    __tablename__ = "seller_balances"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), unique=True, nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    pending_balance: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    total_earnings: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    total_payouts: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    seller: Mapped["Seller"] = relationship()

class SellerPayout(Base, TimestampMixin):
    __tablename__ = "seller_payouts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    payout_method: Mapped[Optional[str]] = mapped_column(String(100))
    payout_details: Mapped[Optional[dict]] = mapped_column(JSON)
    processed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    seller: Mapped["Seller"] = relationship()

# Donations
class DonationProfile(Base, TimestampMixin):
    __tablename__ = "donation_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    cover_url: Mapped[Optional[str]] = mapped_column(String(500))
    goal_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    current_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    total_donations: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    message_template: Mapped[Optional[str]] = mapped_column(Text)
    user: Mapped["User"] = relationship()

class DonationPreset(Base, TimestampMixin):
    __tablename__ = "donation_presets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    label: Mapped[Optional[str]] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Donation(Base, TimestampMixin):
    __tablename__ = "donations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("donation_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    donor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    platform_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    net_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_status: Mapped[str] = mapped_column(String(30), default=PaymentStatus.CREATED.value, index=True)
    payment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"))
    donor_name: Mapped[Optional[str]] = mapped_column(String(150))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    recipient: Mapped["DonationProfile"] = relationship()
    donor: Mapped[Optional["User"]] = relationship()

# Wallet
class Wallet(Base, TimestampMixin):
    __tablename__ = "wallets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    balance: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped["User"] = relationship(back_populates="wallet")
    transactions: Mapped[List["WalletTransaction"]] = relationship(back_populates="wallet", cascade="all, delete-orphan")

class WalletTransaction(Base, TimestampMixin):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50))
    reference_id: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    wallet: Mapped["Wallet"] = relationship(back_populates="transactions")

# Coupons
class Coupon(Base, TimestampMixin):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)  # percentage, fixed
    discount_value: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    min_order_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    max_discount_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    usage_limit: Mapped[Optional[int]] = mapped_column(Integer)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    game_id: Mapped[Optional[int]] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"))
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

class CouponUsage(Base, TimestampMixin):
    __tablename__ = "coupon_usages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), nullable=False)
    __table_args__ = (UniqueConstraint("coupon_id", "order_id", name="uq_coupon_usages_coupon_order"),)

# Promotions
class Promotion(Base, TimestampMixin):
    __tablename__ = "promotions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500))
    promotion_type: Mapped[str] = mapped_column(String(50), default="GENERAL")
    discount_type: Mapped[Optional[str]] = mapped_column(String(20))
    discount_value: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(20, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    target_url: Mapped[Optional[str]] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

# Favorites, Reviews, Notifications, Support, Media, Ledger, Audit, Settings
class Favorite(Base, TimestampMixin):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # game, product, listing
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    __table_args__ = (UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_favorites_user_entity"),)

class Review(Base, TimestampMixin):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_reviews_user_listing"),)

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSON)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="GENERAL")
    status: Mapped[str] = mapped_column(String(30), default=TicketStatus.OPEN.value, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM")
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    messages: Mapped[List["SupportMessage"]] = relationship(back_populates="ticket", cascade="all, delete-orphan")

class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    attachment_url: Mapped[Optional[str]] = mapped_column(String(500))
    ticket: Mapped["SupportTicket"] = relationship(back_populates="messages")

class Media(Base, TimestampMixin):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    alt_text: Mapped[Optional[str]] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    game_id: Mapped[Optional[int]] = mapped_column(ForeignKey("games.id", ondelete="SET NULL"))
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

class RevenueLedger(Base, TimestampMixin):
    __tablename__ = "revenue_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50))
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    gross_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    supplier_cost: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    payment_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    platform_fee: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    commission_amount: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    net_revenue: Mapped[Decimal] = mapped_column(DECIMAL(20, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(10), default="UZS")
    description: Mapped[Optional[str]] = mapped_column(String(500))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(JSON)
    new_value: Mapped[Optional[dict]] = mapped_column(JSON)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

class Setting(Base, TimestampMixin):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
