"""Supplier abstraction. Never fake delivery."""
from __future__ import annotations


class SupplierError(Exception):
    pass


class SupplierAdapter:
    name = "base"

    def __init__(self, supplier=None):
        self.supplier = supplier

    def is_configured(self) -> bool:
        return False

    def get_balance(self) -> dict:
        raise NotImplementedError

    def get_products(self) -> list:
        raise NotImplementedError

    def create_order(self, reference: str, payload: str) -> dict:
        raise NotImplementedError

    def get_order_status(self, external_id: str) -> dict:
        raise NotImplementedError

    def cancel_order(self, external_id: str) -> dict:
        raise NotImplementedError


_ADAPTERS: dict[str, type[SupplierAdapter]] = {}


def register(cls):
    _ADAPTERS[cls.name] = cls
    return cls


def get_adapter(supplier) -> SupplierAdapter | None:
    if supplier is None:
        from app.suppliers.manual import ManualAdapter
        return ManualAdapter(None)
    cls = _ADAPTERS.get(getattr(supplier, "adapter", "") or "")
    if not cls:
        from app.suppliers.generic import GenericHttpAdapter
        cls = GenericHttpAdapter
    return cls(supplier)
