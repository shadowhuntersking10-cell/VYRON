from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal

class GameCategoryResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True

class GameFieldResponse(BaseModel):
    id: int
    field_key: str
    label: str
    placeholder: Optional[str] = None
    field_type: str
    required: bool
    validation_regex: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True

class GameResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    banner_url: Optional[str] = None
    category_id: Optional[int] = None
    status: str
    featured: bool
    popular: bool
    sort_order: int
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    category: Optional[GameCategoryResponse] = None
    fields: List[GameFieldResponse] = []
    products_count: Optional[int] = 0

    class Config:
        from_attributes = True

class GameCreateRequest(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    short_description: Optional[str] = None
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    banner_url: Optional[str] = None
    category_id: Optional[int] = None
    status: str = "ACTIVE"
    featured: bool = False
    popular: bool = False
    sort_order: int = 0
    required_fields_schema: Optional[Dict[str, Any]] = None
    supplier_id: Optional[int] = None

class GameUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    short_description: Optional[str] = None
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    banner_url: Optional[str] = None
    category_id: Optional[int] = None
    status: Optional[str] = None
    featured: Optional[bool] = None
    popular: Optional[bool] = None
    sort_order: Optional[int] = None
