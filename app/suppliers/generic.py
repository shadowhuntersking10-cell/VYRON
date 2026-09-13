"""Generic HTTP supplier (configure SUPPLIER_API_URL / SUPPLIER_API_KEY).

Expected supplier API (JSON):
  GET  {url}/balance                       -> {"balance": "..", "currency": "USD"}
  GET  {url}/products/{id}                 -> {"id": "..", "price": "..", ...}
  POST {url}/orders                        -> {"order_id": "..", "status": ".."}
  GET  {url}/orders/{id}                   -> {"status": "COMPLETED|..."}
  POST {url}/orders/{id}/cancel            -> {"ok": true}

Auth: Bearer <SUPPLIER_API_KEY>. Idempotency-Key header is sent.
"""
from __future__ import annotations

from decimal import Decimal

import httpx

from app.config import settings
from app.suppliers.base import SupplierError, SupplierOrderResult, SupplierProvider, SupplierStatusResult


class GenericSupplier(SupplierProvider):
    code = "generic"

    def __init__(self) -> None:
        self.api_url = (settings.SUPPLIER_API_URL or "").rstrip("/")
        self.api_key = settings.SUPPLIER_API_KEY
        self.api_secret = settings.SUPPLIER_API_SECRET

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    def _headers(self, idempotency_key: str = "") -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def get_balance(self) -> tuple[Decimal, str]:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.api_url}/balance", headers=self._headers())
        except Exception as exc:
            raise SupplierError(f"supplier network error: {exc}") from exc
        if resp.status_code != 200:
            raise SupplierError(f"supplier http {resp.status_code}")
        data = resp.json()
        return Decimal(str(data.get("balance", 0))), str(data.get("currency", "USD"))

    async def get_product(self, external_id: str) -> dict | None:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.api_url}/products/{external_id}", headers=self._headers())
        except Exception as exc:
            raise SupplierError(f"supplier network error: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise SupplierError(f"supplier http {resp.status_code}")
        return resp.json()

    async def create_order(self, *, external_product_id, customer_fields, quantity=1, idempotency_key="") -> SupplierOrderResult:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.api_url}/orders",
                    headers=self._headers(idempotency_key),
                    json={
                        "product_id": external_product_id,
                        "fields": customer_fields,
                        "quantity": quantity,
                    },
                )
        except Exception as exc:
            raise SupplierError(f"supplier network error: {exc}") from exc
        if resp.status_code not in (200, 201):
            raise SupplierError(f"supplier http {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        return SupplierOrderResult(
            ok=True, external_order_id=str(data.get("order_id") or data.get("id") or ""),
            status=str(data.get("status", "PROCESSING")).upper(), raw=data,
        )

    async def get_order_status(self, external_order_id: str) -> SupplierStatusResult:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self.api_url}/orders/{external_order_id}", headers=self._headers())
        except Exception as exc:
            raise SupplierError(f"supplier network error: {exc}") from exc
        if resp.status_code != 200:
            raise SupplierError(f"supplier http {resp.status_code}")
        data = resp.json()
        return SupplierStatusResult(status=str(data.get("status", "PROCESSING")).upper(), raw=data)

    async def cancel_order(self, external_order_id: str) -> bool:
        self.require_configured()
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{self.api_url}/orders/{external_order_id}/cancel", headers=self._headers())
        except Exception as exc:
            raise SupplierError(f"supplier network error: {exc}") from exc
        return resp.status_code in (200, 201)
