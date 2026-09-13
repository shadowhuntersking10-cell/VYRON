from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class ProductResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    game_id: int
    category: Optional[str] = None
    supplier_cost: Decimal
    currency: str
    customer_price: Decimal
    old_price: Optional[Decimal] = None
    image_url: Optional[str] = None
    featured: bool
    popular: bool
    is_active: bool
    stock_status: str
    game_name: Optional[str] = None
    game_slug: Optional[str] = None
    game_logo: Optional[str] = None
    discount_percent: Optional[float] = None

    class Config:
        from_attributes = True

class ProductCreateRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    game_id: int
    category: Optional[str] = None
    supplier_id: Optional[int] = None
    supplier_product_id: Optional[str] = None
    supplier_cost: Decimal
    customer_price: Decimal
    old_price: Optional[Decimal] = None
    currency: str = "UZS"
    image_url: Optional[str] = None
    featured: bool = False
    popular: bool = False
    is_active: bool = True

class PricingPreviewResponse(BaseModel):
    supplier_cost: Decimal
    payment_fee: Decimal
    platform_fee: Decimal
    safety_buffer: Decimal
    minimum_safe_price: Decimal
    suggested_price: Decimal
    current_price: Decimal
    new_price: Optional[Decimal] = None
    expected_profit: Decimal
    expected_margin_percent: float
    is_loss: bool
    is_below_min_margin: bool
    warning: Optional[str] = None
