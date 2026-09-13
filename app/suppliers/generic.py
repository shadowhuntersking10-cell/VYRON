"""Generic HTTP supplier adapter (configurable authorized supplier API)."""
from __future__ import annotations

import json

import httpx

from app.suppliers.base import SupplierAdapter, SupplierError, register


@register
class GenericHttpAdapter(SupplierAdapter):
    name = "generic_http"

    def is_configured(self) -> bool:
        return bool(self.supplier and self.supplier.api_url and self.supplier.api_key and self.supplier.is_active)

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.supplier.api_url.rstrip("/"),
                            headers={"Authorization": f"Bearer {self.supplier.api_key}"},
                            timeout=20.0)

    def get_balance(self) -> dict:
        if not self.is_configured():
            raise SupplierError("supplier_not_configured")
        with self._client() as c:
            r = c.get("/balance")
            r.raise_for_status()
            return r.json()

    def get_products(self) -> list:
        if not self.is_configured():
            raise SupplierError("supplier_not_configured")
        with self._client() as c:
            r = c.get("/products")
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else data.get("products", [])

    def create_order(self, reference: str, payload: str) -> dict:
        if not self.is_configured():
            raise SupplierError("supplier_not_configured")
        body = {"reference": reference, "payload": json.loads(payload or "{}")}
        with self._client() as c:
            r = c.post("/orders", json=body)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict) or not data.get("external_id"):
                raise SupplierError("supplier_bad_response")
            return data

    def get_order_status(self, external_id: str) -> dict:
        if not self.is_configured():
            raise SupplierError("supplier_not_configured")
        with self._client() as c:
            r = c.get(f"/orders/{external_id}")
            r.raise_for_status()
            return r.json()

    def cancel_order(self, external_id: str) -> dict:
        if not self.is_configured():
            raise SupplierError("supplier_not_configured")
        with self._client() as c:
            r = c.post(f"/orders/{external_id}/cancel")
            r.raise_for_status()
            return r.json()
