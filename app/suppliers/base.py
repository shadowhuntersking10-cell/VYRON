"""Supplier provider abstraction. Never fake success: unconfigured
providers raise SupplierNotConfigured and orders go to MANUAL_REVIEW /
SUPPLIER_NOT_CONFIGURED."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


class SupplierNotConfigured(RuntimeError):
    pass


class SupplierError(RuntimeError):
    pass


@dataclass
class SupplierOrderResult:
    ok: bool
    external_order_id: str | None = None
    status: str = "QUEUED"  # QUEUED|PROCESSING|COMPLETED|FAILED
    raw: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class SupplierStatusResult:
    status: str  # QUEUED|PROCESSING|COMPLETED|FAILED|CANCELLED
    raw: dict[str, Any] = field(default_factory=dict)


class SupplierProvider:
    code: str = "base"

    @property
    def configured(self) -> bool:
        return False

    def require_configured(self) -> None:
        if not self.configured:
            raise SupplierNotConfigured(f"Supplier not configured: {self.code}")

    async def get_balance(self) -> tuple[Decimal, str]:
        raise NotImplementedError

    async def get_product(self, external_id: str) -> dict | None:
        raise NotImplementedError

    async def get_products(self) -> list[dict]:
        """List supplier-side products (sync catalogue). Default: unsupported."""
        return []

    async def create_order(
        self, *, external_product_id: str, customer_fields: dict,
        quantity: int = 1, idempotency_key: str = "",
    ) -> SupplierOrderResult:
        raise NotImplementedError

    async def get_order_status(self, external_order_id: str) -> SupplierStatusResult:
        raise NotImplementedError

    async def cancel_order(self, external_order_id: str) -> bool:
        raise NotImplementedError
