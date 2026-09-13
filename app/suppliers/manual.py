"""Manual supplier: always routes orders to MANUAL_REVIEW (human fulfils)."""
from __future__ import annotations

from decimal import Decimal

from app.suppliers.base import SupplierOrderResult, SupplierProvider, SupplierStatusResult


class ManualSupplier(SupplierProvider):
    code = "manual"

    @property
    def configured(self) -> bool:
        return True  # manual fulfilment is always "available"

    async def get_balance(self) -> tuple[Decimal, str]:
        return Decimal("0"), "USD"

    async def get_product(self, external_id: str) -> dict | None:
        return None

    async def create_order(self, *, external_product_id, customer_fields, quantity=1, idempotency_key="") -> SupplierOrderResult:
        return SupplierOrderResult(ok=True, external_order_id=None, status="QUEUED",
                                   raw={"mode": "manual", "note": "Awaiting manual fulfilment"})

    async def get_order_status(self, external_order_id: str) -> SupplierStatusResult:
        return SupplierStatusResult(status="QUEUED", raw={"mode": "manual"})

    async def cancel_order(self, external_order_id: str) -> bool:
        return True
