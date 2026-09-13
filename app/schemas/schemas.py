"""Pydantic v2 request/response schemas."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=255)  # username or email
    password: str = Field(min_length=1, max_length=128)


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: int
    username: str
    email: str
    display_name: str = ""
    avatar: str = ""
    lang: str = "uz"
    theme: str = "system"
    roles: list[str] = []


# ---------- Catalog ----------
class GameOut(ORMModel):
    id: int
    name: str
    slug: str
    description: str = ""
    logo: str = ""
    cover: str = ""
    banner: str = ""
    status: str
    featured: bool
    popular: bool


class ProductOut(ORMModel):
    id: int
    game_id: int | None
    name: str
    slug: str
    description: str = ""
    category: str
    currency: str
    customer_price: Decimal
    old_price: Decimal = Decimal("0")
    status: str
    stock_status: str
    image: str = ""
    featured: bool
    popular: bool


class PricePreview(BaseModel):
    supplier_cost: Decimal
    payment_fee: Decimal
    platform_fee: Decimal
    safety_buffer: Decimal
    minimum_safe_price: Decimal
    suggested_price: Decimal
    current_price: Decimal
    new_price: Decimal | None = None
    expected_profit: Decimal
    expected_margin_percent: Decimal
    max_safe_discount: Decimal
    blocked: bool = False
    warning: str = ""


# ---------- Checkout / orders ----------
class CheckoutItem(BaseModel):
    product_id: int | None = None
    variant_id: int | None = None
    listing_id: int | None = None
    quantity: int = 1


class CheckoutIn(BaseModel):
    items: list[CheckoutItem]
    coupon_code: str = ""
    provider: str = "payme"  # payme/click/stripe/stars/wallet
    customer_fields: dict[str, Any] = {}
    idempotency_key: str = ""


class OrderOut(ORMModel):
    id: int
    public_id: str
    status: str
    currency: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    kind: str


# ---------- Marketplace ----------
class ListingIn(BaseModel):
    category_id: int | None = None
    title: str = Field(min_length=3, max_length=255)
    description: str = ""
    price: Decimal = Decimal("0")
    stock: int = 1


class ReviewIn(BaseModel):
    order_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = ""


# ---------- Donations ----------
class DonateIn(BaseModel):
    amount: Decimal
    message: str = ""
    is_anonymous: bool = False
    donor_name: str = ""
    provider: str = "payme"


# ---------- Support ----------
class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    category: str = "general"
    body: str = Field(min_length=1)


class MessageIn(BaseModel):
    body: str = Field(min_length=1)


# ---------- Wallet ----------
class DepositIn(BaseModel):
    amount: Decimal
    provider: str = "payme"
