from __future__ import annotations
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Any, Optional

class PaymentProviderBase(ABC):
    provider_name: str = "BASE"

    @abstractmethod
    async def create_payment(self, order_id: int, amount: Decimal, currency: str, **kwargs) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def verify_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> tuple[bool, str]:
        pass

    @abstractmethod
    async def check_payment_status(self, provider_payment_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def refund(self, provider_payment_id: str, amount: Decimal, reason: Optional[str] = None) -> Dict[str, Any]:
        pass

    def is_configured(self) -> bool:
        return False
