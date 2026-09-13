from __future__ import annotations
from typing import Optional, Any, List, Generic, TypeVar
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = 1
    per_page: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    @property
    def limit(self) -> int:
        return self.per_page

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int

class MessageResponse(BaseModel):
    message: str
    success: bool = True

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None

class MoneyBreakdown(BaseModel):
    supplier_cost: Decimal
    payment_fee: Decimal
    platform_fee: Decimal
    safety_buffer: Decimal
    minimum_safe_price: Decimal
    suggested_price: Decimal
    current_price: Optional[Decimal] = None
    expected_profit: Decimal
    margin_percent: Optional[float] = None
