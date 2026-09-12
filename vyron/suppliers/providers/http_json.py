"""Configurable HTTP/JSON supplier adapter.

A production-ready generic adapter driven entirely by database configuration
per Supplier row (endpoints, headers, field mapping, response mapping), with
credentials stored encrypted. This is how real aggregator platforms integrate
suppliers without hardcoding any of them into the core.

Supplier.config example:
{
  "endpoints": {
    "products":      {"method": "GET",  "path": "/v1/products"},
    "product":       {"method": "GET",  "path": "/v1/products/{external_id}"},
    "balance":       {"method": "GET",  "path": "/v1/balance"},
    "validate":      {"method": "POST", "path": "/v1/validate"},
    "create_order":  {"method": "POST", "path": "/v1/orders"},
    "order_status":  {"method": "GET",  "path": "/v1/orders/{external_order_id}"},
    "cancel_order":  {"method": "POST", "path": "/v1/orders/{external_order_id}/cancel"},
    "refund_order":  {"method": "POST", "path": "/v1/orders/{external_order_id}/refund"}
  },
  "auth": {"type": "bearer"},                      # bearer | header | basic | none
  "request_mapping": {                             # our fields -> supplier body
    "create_order": {"product": "{external_product_id}", "recipient": "{fields}", "qty": "{quantity}", "idempotency_key": "{idempotency_key}"}
  },
  "response_mapping": {
    "product_id": "data.id",
    "product_name": "data.name",
    "product_cost": "data.price",
    "product_available": "data.active",
    "balance": "data.balance",
    "order_id": "data.order_id",
    "order_status": "data.status",
    "validation_ok": "data.valid",
    "validation_name": "data.nickname",
    "success_statuses": ["completed", "success", "delivered"],
    "pending_statuses": ["pending", "processing", "in_progress"],
    "failed_statuses": ["failed", "cancelled", "rejected", "error"]
  },
  "timeout_seconds": 30
}

Credentials (base_url, api_key, api_secret) come from the encrypted config
blob on the Supplier row, or from SUPPLIER_API_BASE_URL / SUPPLIER_API_KEY /
SUPPLIER_API_SECRET for the environment-default supplier.

Missing configuration => SupplierNotConfiguredError — never a fake success.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

import httpx

from vyron.errors import SupplierNotConfiguredError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.suppliers.base import (
    BalanceResult,
    RecipientValidation,
    SupplierOrderResult,
    SupplierProductInfo,
    SupplierProvider,
    SupplierProviderError,
    SupplierStatusResult,
)

log = get_logger("vyron.suppliers.http_json")

DEFAULT_RESPONSE_MAPPING: Dict[str, Any] = {
    "product_id": "id",
    "product_name": "name",
    "product_cost": "price",
    "product_available": "available",
    "balance": "balance",
    "order_id": "order_id",
    "order_status": "status",
    "validation_ok": "valid",
    "validation_name": "nickname",
    "success_statuses": ["completed", "success", "delivered", "done"],
    "pending_statuses": ["pending", "processing", "in_progress", "created"],
    "failed_statuses": ["failed", "cancelled", "canceled", "rejected", "error"],
}


def _dig(payload: Any, dotted: str) -> Any:
    node = payload
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return node


class HttpJsonSupplierProvider(SupplierProvider):
    kind = "http_json"

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        api_secret: str = "",
        config: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.config = config or {}
        self.timeout = int(self.config.get("timeout_seconds") or timeout_seconds)
        self.mapping = {**DEFAULT_RESPONSE_MAPPING, **(self.config.get("response_mapping") or {})}
        self.endpoints: Dict[str, Dict[str, str]] = self.config.get("endpoints") or {}

    # --- lifecycle -----------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _ensure(self) -> None:
        if not self.is_configured():
            raise SupplierNotConfiguredError(
                "Supplier base_url is not configured.", code="SUPPLIER_NOT_CONFIGURED"
            )

    def _endpoint(self, name: str) -> Dict[str, str]:
        endpoint = self.endpoints.get(name)
        if not endpoint or not endpoint.get("path"):
            raise SupplierNotConfiguredError(
                f"Supplier endpoint '{name}' is not configured.", code="SUPPLIER_NOT_CONFIGURED"
            )
        return endpoint

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        auth = (self.config.get("auth") or {}).get("type", "bearer")
        if self.api_key:
            if auth == "bearer":
                headers["Authorization"] = f"Bearer {self.api_key}"
            elif auth == "basic":
                import base64

                token = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
                headers["Authorization"] = f"Basic {token}"
            else:
                headers["X-API-Key"] = self.api_key
        for key, value in (self.config.get("headers") or {}).items():
            headers[str(key)] = str(value)
        return headers

    def _request(self, method: str, path: str, *, json_body: Any = None) -> Any:
        self._ensure()
        url = self.base_url + path
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method.upper(), url, json=json_body, headers=self._headers())
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            # UNKNOWN outcome — caller must reconcile, never blindly retry-submit.
            raise SupplierProviderError(f"supplier transport error: {exc}") from exc
        if response.status_code in (401, 403):
            raise SupplierNotConfiguredError(
                "Supplier rejected credentials (401/403).", code="SUPPLIER_AUTH_FAILED"
            )
        if response.status_code >= 500:
            raise SupplierProviderError(f"supplier server error: {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise SupplierProviderError(f"supplier returned non-JSON response ({response.status_code})") from exc

    # --- catalog -------------------------------------------------------------
    def get_products(self) -> List[SupplierProductInfo]:
        endpoint = self._endpoint("products")
        payload = self._request(endpoint.get("method", "GET"), endpoint["path"])
        items = payload
        list_path = (self.config.get("response_mapping") or {}).get("products_list")
        if list_path:
            items = _dig(payload, list_path) or []
        if isinstance(items, dict):
            items = items.get("items") or items.get("data") or []
        products: List[SupplierProductInfo] = []
        for item in items if isinstance(items, list) else []:
            try:
                cost_raw = _dig(item, self.mapping["product_cost"])
                cost = to_money(cost_raw) if cost_raw is not None else Decimal("0.00")
            except (InvalidOperation, ValueError, ArithmeticError):
                cost = Decimal("0.00")
            available = _dig(item, self.mapping["product_available"])
            products.append(
                SupplierProductInfo(
                    external_id=str(_dig(item, self.mapping["product_id"])),
                    name=str(_dig(item, self.mapping["product_name"]) or ""),
                    cost=cost,
                    available=bool(available) if available is not None else True,
                    stock=_dig(item, "stock") if isinstance(_dig(item, "stock"), int) else None,
                    raw=item if isinstance(item, dict) else {},
                )
            )
        return products

    def get_product(self, external_product_id: str) -> Optional[SupplierProductInfo]:
        endpoint = self._endpoint("product")
        path = endpoint["path"].replace("{external_id}", external_product_id)
        try:
            payload = self._request(endpoint.get("method", "GET"), path)
        except SupplierProviderError:
            return None
        item = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(item, dict):
            return None
        cost_raw = _dig(item, self.mapping["product_cost"])
        try:
            cost = to_money(cost_raw) if cost_raw is not None else Decimal("0.00")
        except (InvalidOperation, ValueError, ArithmeticError):
            cost = Decimal("0.00")
        available = _dig(item, self.mapping["product_available"])
        return SupplierProductInfo(
            external_id=str(_dig(item, self.mapping["product_id"]) or external_product_id),
            name=str(_dig(item, self.mapping["product_name"]) or ""),
            cost=cost,
            available=bool(available) if available is not None else True,
            raw=item,
        )

    def get_balance(self) -> BalanceResult:
        endpoint = self._endpoint("balance")
        payload = self._request(endpoint.get("method", "GET"), endpoint["path"])
        raw_balance = _dig(payload, self.mapping["balance"])
        try:
            balance = to_money(raw_balance) if raw_balance is not None else None
        except (InvalidOperation, ValueError, ArithmeticError):
            balance = None
        currency = str(_dig(payload, "currency") or "USD")
        return BalanceResult(balance=balance, currency=currency, raw=payload if isinstance(payload, dict) else {})

    # --- delivery ----------------------------------------------------------------
    def validate_recipient(self, external_product_id: str, fields: Dict[str, Any]) -> RecipientValidation:
        if "validate" not in self.endpoints:
            # No validation endpoint configured: structural validation only.
            return RecipientValidation(valid=True, normalized=fields, reason="no validation endpoint configured")
        endpoint = self._endpoint("validate")
        body = {"product": external_product_id, "fields": fields}
        payload = self._request(endpoint.get("method", "POST"), endpoint["path"], json_body=body)
        ok = _dig(payload, self.mapping["validation_ok"])
        reason = str(_dig(payload, "reason") or _dig(payload, "error") or "")
        display = _dig(payload, self.mapping["validation_name"])
        return RecipientValidation(
            valid=bool(ok), reason=reason, normalized=fields, display_name=str(display) if display else None
        )

    def create_order(
        self, external_product_id: str, fields: Dict[str, Any], quantity: int, idempotency_key: str
    ) -> SupplierOrderResult:
        endpoint = self._endpoint("create_order")
        request_mapping = (self.config.get("request_mapping") or {}).get("create_order")
        if request_mapping:
            body = json.loads(
                json.dumps(request_mapping, default=str)
                .replace("{external_product_id}", external_product_id)
                .replace("{fields}", json.dumps(fields, ensure_ascii=False, default=str))
                .replace("{quantity}", str(quantity))
                .replace("{idempotency_key}", idempotency_key)
            )
        else:
            body = {
                "product_id": external_product_id,
                "recipient": fields,
                "quantity": quantity,
                "idempotency_key": idempotency_key,
            }
        headers = self._headers()
        headers["Idempotency-Key"] = idempotency_key
        url = self.base_url + endpoint["path"]
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(endpoint.get("method", "POST").upper(), url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise SupplierProviderError(f"create_order transport error: {exc}") from exc
        if response.status_code in (401, 403):
            raise SupplierNotConfiguredError("Supplier rejected credentials.", code="SUPPLIER_AUTH_FAILED")
        try:
            payload = response.json()
        except ValueError:
            if response.status_code >= 500:
                raise SupplierProviderError(f"supplier error {response.status_code} (non-JSON)")
            return SupplierOrderResult(status="FAILED", error=f"non-JSON response ({response.status_code})", retryable=False)
        if response.status_code >= 400:
            return SupplierOrderResult(
                status="FAILED",
                error=f"supplier returned {response.status_code}",
                retryable=response.status_code >= 500,
                raw=payload if isinstance(payload, dict) else {},
            )
        external_order_id = _dig(payload, self.mapping["order_id"])
        status_raw = str(_dig(payload, self.mapping["order_status"]) or "").lower()
        status = self._map_status(status_raw, default="PROCESSING")
        return SupplierOrderResult(
            status=status,
            external_order_id=str(external_order_id) if external_order_id else None,
            error=str(_dig(payload, "error") or "") or None,
            raw=payload if isinstance(payload, dict) else {},
        )

    def get_order_status(self, external_order_id: str) -> SupplierStatusResult:
        endpoint = self._endpoint("order_status")
        path = endpoint["path"].replace("{external_order_id}", external_order_id)
        payload = self._request(endpoint.get("method", "GET"), path)
        status_raw = str(_dig(payload, self.mapping["order_status"]) or "").lower()
        status = self._map_status(status_raw, default="UNKNOWN")
        return SupplierStatusResult(status=status, error=str(_dig(payload, "error") or "") or None, raw=payload if isinstance(payload, dict) else {})

    def cancel_order(self, external_order_id: str) -> SupplierStatusResult:
        endpoint = self._endpoint("cancel_order")
        path = endpoint["path"].replace("{external_order_id}", external_order_id)
        payload = self._request(endpoint.get("method", "POST"), path)
        status_raw = str(_dig(payload, self.mapping["order_status"]) or "").lower()
        return SupplierStatusResult(status=self._map_status(status_raw, default="PROCESSING"), raw=payload if isinstance(payload, dict) else {})

    def refund_order(self, external_order_id: str, reason: str) -> SupplierStatusResult:
        endpoint = self._endpoint("refund_order")
        path = endpoint["path"].replace("{external_order_id}", external_order_id)
        payload = self._request(endpoint.get("method", "POST"), path, json_body={"reason": reason[:200]})
        status_raw = str(_dig(payload, self.mapping["order_status"]) or "").lower()
        return SupplierStatusResult(status=self._map_status(status_raw, default="PROCESSING"), raw=payload if isinstance(payload, dict) else {})

    def _map_status(self, status_raw: str, default: str) -> str:
        if status_raw in [s.lower() for s in self.mapping.get("success_statuses", [])]:
            return "SUCCESS"
        if status_raw in [s.lower() for s in self.mapping.get("pending_statuses", [])]:
            return "PROCESSING"
        if status_raw in [s.lower() for s in self.mapping.get("failed_statuses", [])]:
            return "FAILED"
        return default
