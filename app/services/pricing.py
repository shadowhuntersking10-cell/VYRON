from __future__ import annotations
from decimal import Decimal
from typing import Dict
from app.utils.helpers import calculate_pricing, to_decimal, quantize_money
from app.config import settings

class PricingService:
    @staticmethod
    def calculate_product_pricing(
        supplier_cost: Decimal,
        payment_fee_percent: Decimal | None = None,
        payment_fixed_fee: Decimal | None = None,
        safety_buffer_percent: Decimal | None = None,
        platform_margin_percent: Decimal | None = None,
        commission_percent: Decimal = Decimal("0.0")
    ) -> Dict:
        return calculate_pricing(
            supplier_cost=supplier_cost,
            payment_fee_percent=payment_fee_percent or to_decimal(settings.DEFAULT_PAYMENT_FEE_PERCENT),
            payment_fixed_fee=payment_fixed_fee or to_decimal(settings.DEFAULT_PAYMENT_FIXED_FEE),
            safety_buffer_percent=safety_buffer_percent or to_decimal(settings.DEFAULT_SAFETY_BUFFER_PERCENT),
            platform_margin_percent=platform_margin_percent or to_decimal(settings.DEFAULT_PLATFORM_MARGIN_PERCENT),
            commission_percent=commission_percent
        )

    @staticmethod
    def validate_price(
        supplier_cost: Decimal,
        customer_price: Decimal,
        min_margin_percent: Decimal | None = None
    ) -> Dict:
        pricing = PricingService.calculate_product_pricing(supplier_cost)
        min_safe = pricing["minimum_safe_price"]
        suggested = pricing["suggested_price"]
        
        customer_price = to_decimal(customer_price)
        min_margin_percent = min_margin_percent or to_decimal(settings.DEFAULT_MIN_MARGIN_PERCENT)

        is_loss = customer_price < min_safe
        # Calculate margin
        profit = customer_price - pricing["supplier_cost"] - pricing["payment_fee"] - pricing["safety_buffer"]
        margin_percent = (profit / customer_price * Decimal("100")) if customer_price > 0 else Decimal("0")
        margin_percent = quantize_money(margin_percent)

        is_below_min_margin = margin_percent < min_margin_percent

        warning = None
        if is_loss:
            warning = f"LOSS: Price {customer_price} is below minimum safe price {min_safe}"
        elif is_below_min_margin:
            warning = f"LOW MARGIN: Margin {margin_percent}% is below minimum {min_margin_percent}%"

        return {
            **pricing,
            "current_price": customer_price,
            "expected_profit": quantize_money(profit),
            "expected_margin_percent": float(margin_percent),
            "is_loss": is_loss,
            "is_below_min_margin": is_below_min_margin,
            "warning": warning,
            "can_save": not is_loss,  # Block if loss unless override
        }

    @staticmethod
    def calculate_donation_fees(amount: Decimal, fee_percent: Decimal | None = None) -> Dict:
        fee_percent = fee_percent or to_decimal(settings.DEFAULT_DONATION_FEE)
        amount = to_decimal(amount)
        fee = amount * fee_percent / Decimal("100")
        net = amount - fee
        return {
            "gross": quantize_money(amount),
            "fee_percent": fee_percent,
            "fee": quantize_money(fee),
            "net": quantize_money(net)
        }

    @staticmethod
    def calculate_marketplace_commission(amount: Decimal, commission_rate: Decimal | None = None) -> Dict:
        commission_rate = commission_rate or to_decimal(settings.DEFAULT_MARKETPLACE_COMMISSION)
        amount = to_decimal(amount)
        commission = amount * commission_rate / Decimal("100")
        seller_earnings = amount - commission
        return {
            "gross": quantize_money(amount),
            "commission_rate": commission_rate,
            "commission": quantize_money(commission),
            "seller_earnings": quantize_money(seller_earnings)
        }
