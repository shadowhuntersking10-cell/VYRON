"""Manual fulfillment adapter: always routes to MANUAL_REVIEW, never fakes."""
from __future__ import annotations

from app.suppliers.base import SupplierAdapter, SupplierError, register


@register
class ManualAdapter(SupplierAdapter):
    name = "manual"

    def is_configured(self) -> bool:
        return False  # forces MANUAL_REVIEW honestly

    def _raise(self):
        raise SupplierError("manual_fulfillment_required")

    def get_balance(self): return self._raise()
    def get_products(self): return self._raise()
    def create_order(self, reference, payload): return self._raise()
    def get_order_status(self, external_id): return self._raise()
    def cancel_order(self, external_id): return self._raise()
