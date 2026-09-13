from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

class OrderItemRequest(BaseModel):
    product_id: int
    quantity: int = 1
    game_data: Optional[Dict[str, Any]] = None  # player_id, region, etc

class CheckoutRequest(BaseModel):
    items: List[OrderItemRequest]
    coupon_code: Optional[str] = None
    payment_provider: str = "PAYME"
    game_data: Optional[Dict[str, Any]] = None

class OrderItemResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: int
    order_number: str
    status: str
    currency: str
    subtotal: Decimal
    discount_amount: Decimal
    service_fee: Decimal
    total_amount: Decimal
    payment_provider: Optional[str] = None
    coupon_code: Optional[str] = None
    game_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True
