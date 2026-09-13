"""Pydantic schemas for API I/O."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator


class UserOut(BaseModel):
    id: int
    email: str | None = None
    username: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    role: str
    lang: str = "uz"
    theme: str = "system"
    is_active: bool = True

    model_config = {"from_attributes": True}


class RegisterIn(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=72)
    password_confirm: str | None = Field(default=None, max_length=72)
    full_name: str | None = Field(default=None, max_length=255)
    lang: str = "uz"

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password_confirm is not None and self.password_confirm != self.password:
            raise ValueError("passwords_do_not_match")
        return self


class LoginIn(BaseModel):
    login: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class TelegramAuthIn(BaseModel):
    init_data: str = Field(min_length=10)


class GameOut(BaseModel):
    id: int
    slug: str
    title: str
    description: str | None = None
    category_id: int | None = None
    logo_url: str | None = None
    banner_url: str | None = None
    fields_schema: list = []
    is_active: bool = True
    is_featured: bool = False

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    id: int
    game_id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    selling_price: Decimal
    currency: str
    delivery_type: str = "auto"
    stock: int = -1
    is_active: bool = True
    is_popular: bool = False

    model_config = {"from_attributes": True}


class CheckoutQuoteIn(BaseModel):
    product_id: int | None = None
    variant_id: int | None = None
    listing_id: int | None = None
    quantity: int = Field(default=1, ge=1, le=100)
    coupon_code: str | None = None
    customer_fields: dict[str, Any] = {}


class CheckoutQuoteOut(BaseModel):
    title: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    discount: Decimal
    service_fee: Decimal
    total: Decimal
    currency: str
    coupon_applied: str | None = None


class OrderCreateIn(CheckoutQuoteIn):
    provider: str = "payme"
    idempotency_key: str | None = None


class OrderOut(BaseModel):
    id: int
    public_id: str
    status: str
    subtotal: Decimal
    discount: Decimal
    service_fee: Decimal
    total: Decimal
    currency: str
    timeline: list = []
    created_at: dt.datetime
    fx_base_currency: str | None = None
    fx_rate: Decimal | None = None
    fx_quoted_at: dt.datetime | None = None

    model_config = {"from_attributes": True}


class PaymentOut(BaseModel):
    id: int
    provider: str
    status: str
    amount: Decimal
    currency: str
    checkout_url: str | None = None

    model_config = {"from_attributes": True}


class ListingOut(BaseModel):
    id: int
    seller_id: int
    title: str
    description: str | None = None
    images: list = []
    price: Decimal
    currency: str
    category: str
    category_id: int | None = None
    status: str
    views: int = 0
    gallery: list = []

    model_config = {"from_attributes": True}


class SellerOut(BaseModel):
    id: int
    shop_name: str
    description: str | None = None
    avatar_url: str | None = None
    is_verified: bool = False
    rating_avg: Decimal = Decimal("0")
    rating_count: int = 0
    sales_count: int = 0

    model_config = {"from_attributes": True}


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    category: str = "general"
    body: str = Field(min_length=1, max_length=5000)
    order_id: int | None = None
    attachments: list[str] = Field(default_factory=list, max_length=5)


class Page(BaseModel):
    items: list[Any]
    total: int
    page: int
    per_page: int
    pages: int
