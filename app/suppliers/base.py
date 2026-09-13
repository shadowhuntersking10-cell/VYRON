from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, List, Optional

class SupplierBase(ABC):
    code: str = "BASE"
    name: str = "Base Supplier"

    @abstractmethod
    async def get_balance(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_products(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_order(self, product_id: str, quantity: int, game_data: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_order_status(self, supplier_order_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def cancel_order(self, supplier_order_id: str) -> Dict[str, Any]:
        pass

    def is_configured(self) -> bool:
        return False
