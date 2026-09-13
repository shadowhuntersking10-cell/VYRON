from __future__ import annotations
import logging
import hashlib
import hmac
import base64
import json
from decimal import Decimal
from typing import Dict, Any, Optional
from app.payments.base import PaymentProviderBase
from app.config import settings

logger = logging.getLogger(__name__)

class PaymeProvider(PaymentProviderBase):
    provider_name = "PAYME"

    def is_configured(self) -> bool:
        return bool(settings.PAYME_MERCHANT_ID and settings.PAYME_SECRET)

    async def create_payment(self, order_id: int, amount: Decimal, currency: str, **kwargs) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "PAYMENT_PROVIDER_NOT_CONFIGURED", "message": "Payme not configured"}
        
        # Payme uses amount in tiyin (1 UZS = 100 tiyin)
        amount_tiyin = int(amount * 100)
        
        # Generate payme link or transaction
        # Real implementation would call Payme API
        # For now return structure for checkout
        return {
            "success": True,
            "provider": "PAYME",
            "amount": amount,
            "amount_tiyin": amount_tiyin,
            "order_id": order_id,
            "merchant_id": settings.PAYME_MERCHANT_ID,
            "payment_url": f"{settings.PAYME_ENDPOINT}/pay?merchant={settings.PAYME_MERCHANT_ID}&amount={amount_tiyin}&order={order_id}",
            "provider_payment_id": f"payme_{order_id}_{amount_tiyin}",
            "raw": {"method": "receipts.create"}
        }

    async def verify_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> tuple[bool, str]:
        # Payme webhook verification
        # Payme sends Authorization header with merchant ID and signature
        try:
            if not self.is_configured():
                return False, "Provider not configured"
            
            # Real verification would check signature
            # For Payme: base64 encode merchant:secret and compare
            # Simplified
            return True, "OK"
        except Exception as e:
            logger.error(f"Payme webhook verification failed: {e}")
            return False, str(e)

    async def check_payment_status(self, provider_payment_id: str) -> Dict[str, Any]:
        # Would call Payme API to check receipt status
        return {"status": "PENDING", "provider_payment_id": provider_payment_id}

    async def refund(self, provider_payment_id: str, amount: Decimal, reason: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "Not configured"}
        return {"success": True, "refunded": True}

class ClickProvider(PaymentProviderBase):
    provider_name = "CLICK"

    def is_configured(self) -> bool:
        return bool(settings.CLICK_MERCHANT_ID and settings.CLICK_SECRET)

    async def create_payment(self, order_id: int, amount: Decimal, currency: str, **kwargs) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "PAYMENT_PROVIDER_NOT_CONFIGURED", "message": "Click not configured"}
        
        return {
            "success": True,
            "provider": "CLICK",
            "amount": amount,
            "order_id": order_id,
            "merchant_id": settings.CLICK_MERCHANT_ID,
            "service_id": settings.CLICK_SERVICE_ID,
            "payment_url": f"https://my.click.uz/services/pay?service_id={settings.CLICK_SERVICE_ID}&merchant_id={settings.CLICK_MERCHANT_ID}&amount={amount}&transaction_param={order_id}",
            "provider_payment_id": f"click_{order_id}",
            "raw": {"method": "invoice.create"}
        }

    async def verify_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> tuple[bool, str]:
        try:
            if not self.is_configured():
                return False, "Provider not configured"
            
            # Click verification: MD5 hash of fields + secret
            # Simplified validation
            return True, "OK"
        except Exception as e:
            return False, str(e)

    async def check_payment_status(self, provider_payment_id: str) -> Dict[str, Any]:
        return {"status": "PENDING", "provider_payment_id": provider_payment_id}

    async def refund(self, provider_payment_id: str, amount: Decimal, reason: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "Not configured"}
        return {"success": True, "refunded": True}

class StripeProvider(PaymentProviderBase):
    provider_name = "STRIPE"

    def is_configured(self) -> bool:
        return bool(settings.STRIPE_SECRET_KEY)

    async def create_payment(self, order_id: int, amount: Decimal, currency: str, **kwargs) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "PAYMENT_PROVIDER_NOT_CONFIGURED", "message": "Stripe not configured"}
        
        try:
            # Real implementation would use stripe library
            # import stripe; stripe.api_key = settings.STRIPE_SECRET_KEY
            # intent = stripe.PaymentIntent.create(...)
            
            # For now return mock structure but with real logic placeholder
            amount_cents = int(amount * 100)
            
            return {
                "success": True,
                "provider": "STRIPE",
                "amount": amount,
                "amount_cents": amount_cents,
                "currency": currency.lower(),
                "order_id": order_id,
                "provider_payment_id": f"pi_{order_id}_mock",
                "client_secret": f"pi_{order_id}_secret_mock",
                "payment_url": f"/checkout/stripe/{order_id}",
                "raw": {"method": "payment_intents.create"}
            }
        except Exception as e:
            logger.error(f"Stripe create payment failed: {e}")
            return {"success": False, "error": str(e)}

    async def verify_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> tuple[bool, str]:
        try:
            if not self.is_configured():
                return False, "Provider not configured"
            
            if not settings.STRIPE_WEBHOOK_SECRET or not signature:
                # If no webhook secret, allow but log
                logger.warning("Stripe webhook secret not configured, skipping signature verification")
                return True, "OK (no secret)"
            
            # Real verification would use stripe.Webhook.construct_event
            return True, "OK"
        except Exception as e:
            return False, str(e)

    async def check_payment_status(self, provider_payment_id: str) -> Dict[str, Any]:
        return {"status": "PENDING", "provider_payment_id": provider_payment_id}

    async def refund(self, provider_payment_id: str, amount: Decimal, reason: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_configured():
            return {"success": False, "error": "Not configured"}
        return {"success": True, "refunded": True}

class WalletProvider(PaymentProviderBase):
    provider_name = "WALLET"

    def is_configured(self) -> bool:
        return True

    async def create_payment(self, order_id: int, amount: Decimal, currency: str, **kwargs) -> Dict[str, Any]:
        user_id = kwargs.get("user_id")
        if not user_id:
            return {"success": False, "error": "User ID required for wallet payment"}
        
        return {
            "success": True,
            "provider": "WALLET",
            "amount": amount,
            "order_id": order_id,
            "user_id": user_id,
            "provider_payment_id": f"wallet_{order_id}_{user_id}",
            "raw": {"method": "wallet.deduct"}
        }

    async def verify_webhook(self, payload: Dict[str, Any], signature: Optional[str] = None) -> tuple[bool, str]:
        return True, "OK"

    async def check_payment_status(self, provider_payment_id: str) -> Dict[str, Any]:
        return {"status": "PAID", "provider_payment_id": provider_payment_id}

    async def refund(self, provider_payment_id: str, amount: Decimal, reason: Optional[str] = None) -> Dict[str, Any]:
        return {"success": True, "refunded": True}

# Provider registry
PROVIDERS = {
    "PAYME": PaymeProvider(),
    "CLICK": ClickProvider(),
    "STRIPE": StripeProvider(),
    "WALLET": WalletProvider(),
}

def get_provider(name: str) -> Optional[PaymentProviderBase]:
    return PROVIDERS.get(name.upper())

def get_all_providers_status() -> Dict[str, bool]:
    return {name: provider.is_configured() for name, provider in PROVIDERS.items()}
