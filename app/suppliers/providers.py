from __future__ import annotations
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
import httpx
from app.suppliers.base import SupplierBase
from app.config import settings

logger = logging.getLogger(__name__)

class GenericSupplier(SupplierBase):
    code = "GENERIC"
    name = "Generic Supplier"

    def is_configured(self) -> bool:
        return bool(settings.SUPPLIER_API_URL and settings.SUPPLIER_API_KEY and settings.SUPPLIER_ENABLED)

    async def get_balance(self) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "SUPPLIER_NOT_CONFIGURED"}
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.SUPPLIER_API_URL}/balance",
                    headers={"Authorization": f"Bearer {settings.SUPPLIER_API_KEY}"}
                )
                return {"success": True, "balance": resp.json()}
        except Exception as e:
            logger.error(f"Supplier balance check failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_products(self) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []
        
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{settings.SUPPLIER_API_URL}/products",
                    headers={"Authorization": f"Bearer {settings.SUPPLIER_API_KEY}"}
                )
                data = resp.json()
                return data.get("products", []) if isinstance(data, dict) else data
        except Exception as e:
            logger.error(f"Supplier get_products failed: {e}")
            return []

    async def create_order(self, product_id: str, quantity: int, game_data: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        if not self.is_configured():
            return {
                "success": False,
                "error": "SUPPLIER_NOT_CONFIGURED",
                "status": "MANUAL_REVIEW",
                "message": "Supplier not configured, order requires manual review"
            }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                payload = {
                    "product_id": product_id,
                    "quantity": quantity,
                    "game_data": game_data,
                    "idempotency_key": idempotency_key
                }
                resp = await client.post(
                    f"{settings.SUPPLIER_API_URL}/orders",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.SUPPLIER_API_KEY}",
                        "Idempotency-Key": idempotency_key
                    }
                )
                result = resp.json()
                return {
                    "success": resp.status_code in (200, 201),
                    "supplier_order_id": result.get("order_id") or result.get("id"),
                    "status": result.get("status", "PROCESSING"),
                    "raw": result
                }
        except Exception as e:
            logger.error(f"Supplier create_order failed: {e}")
            return {"success": False, "error": str(e), "status": "FAILED"}

    async def get_order_status(self, supplier_order_id: str) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "SUPPLIER_NOT_CONFIGURED"}
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.SUPPLIER_API_URL}/orders/{supplier_order_id}",
                    headers={"Authorization": f"Bearer {settings.SUPPLIER_API_KEY}"}
                )
                return {"success": True, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cancel_order(self, supplier_order_id: str) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "SUPPLIER_NOT_CONFIGURED"}
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{settings.SUPPLIER_API_URL}/orders/{supplier_order_id}/cancel",
                    headers={"Authorization": f"Bearer {settings.SUPPLIER_API_KEY}"}
                )
                return {"success": True, "data": resp.json()}
        except Exception as e:
            return {"success": False, "error": str(e)}

class ManualSupplier(SupplierBase):
    """Fallback supplier that always requires manual review"""
    code = "MANUAL"
    name = "Manual Fulfillment"

    def is_configured(self) -> bool:
        return True

    async def get_balance(self) -> Dict[str, Any]:
        return {"success": True, "balance": "MANUAL", "message": "Manual fulfillment"}

    async def get_products(self) -> List[Dict[str, Any]]:
        return []

    async def create_order(self, product_id: str, quantity: int, game_data: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        return {
            "success": True,
            "supplier_order_id": f"manual_{idempotency_key[:8]}",
            "status": "MANUAL_REVIEW",
            "message": "Order requires manual review - supplier not configured or manual mode"
        }

    async def get_order_status(self, supplier_order_id: str) -> Dict[str, Any]:
        return {"success": True, "status": "MANUAL_REVIEW"}

    async def cancel_order(self, supplier_order_id: str) -> Dict[str, Any]:
        return {"success": True, "status": "CANCELLED"}

SUPPLIERS = {
    "GENERIC": GenericSupplier(),
    "MANUAL": ManualSupplier(),
}

def get_supplier(code: str = None) -> SupplierBase:
    if code and code.upper() in SUPPLIERS:
        supplier = SUPPLIERS[code.upper()]
        if supplier.is_configured():
            return supplier
    # Try generic if configured
    generic = SUPPLIERS["GENERIC"]
    if generic.is_configured():
        return generic
    return SUPPLIERS["MANUAL"]

def get_supplier_status() -> Dict[str, bool]:
    return {code: s.is_configured() for code, s in SUPPLIERS.items()}
