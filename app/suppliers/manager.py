"""SupplierManager: resolves provider per product/game/default."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Game, Product, Supplier
from app.suppliers.base import SupplierProvider
from app.suppliers.generic import GenericSupplier
from app.suppliers.manual import ManualSupplier


class SupplierManager:
    def __init__(self) -> None:
        self._providers: dict[str, SupplierProvider] = {
            "manual": ManualSupplier(),
            "generic": GenericSupplier(),
        }

    def get(self, code: str | None) -> SupplierProvider:
        return self._providers.get((code or "").lower()) or self._providers["manual"]

    def status_list(self) -> list[dict]:
        return [{"code": c, "configured": p.configured} for c, p in self._providers.items()]

    async def provider_for_product(self, db: AsyncSession, product: Product) -> tuple[SupplierProvider, Supplier | None]:
        supplier_row: Supplier | None = None
        code = settings.SUPPLIER_DEFAULT or "manual"
        supplier_id = product.supplier_id
        if not supplier_id and product.game_id:
            game = await db.get(Game, product.game_id)
            supplier_id = game.supplier_id if game else None
        if supplier_id:
            supplier_row = await db.get(Supplier, supplier_id)
            if supplier_row:
                code = supplier_row.code
        return self.get(code), supplier_row


_manager: SupplierManager | None = None


def get_supplier_manager() -> SupplierManager:
    global _manager
    if _manager is None:
        _manager = SupplierManager()
    return _manager
