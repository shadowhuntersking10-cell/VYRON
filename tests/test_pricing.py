from decimal import Decimal
from app.services.pricing import PricingService
from app.utils.helpers import calculate_pricing

def test_minimum_safe_price_protection():
    # Supplier cost 40k, price 46.5k should be safe
    cost = Decimal("40000")
    pricing = PricingService.calculate_product_pricing(cost)
    
    min_safe = pricing["minimum_safe_price"]
    
    # Try to save below min_safe - should be blocked
    validation = PricingService.validate_price(cost, min_safe - Decimal("1000"))
    assert validation["is_loss"] == True
    
    # At min_safe should be OK (not loss, but low margin warning possible)
    validation = PricingService.validate_price(cost, min_safe)
    assert validation["is_loss"] == False

def test_pricing_breakdown():
    cost = Decimal("50000")
    result = calculate_pricing(
        supplier_cost=cost,
        payment_fee_percent=Decimal("2.0"),
        payment_fixed_fee=Decimal("500"),
        safety_buffer_percent=Decimal("2.0"),
        platform_margin_percent=Decimal("10.0")
    )
    
    assert result["supplier_cost"] == Decimal("50000.00")
    assert result["payment_fee"] > 0
    assert result["safety_buffer"] > 0
    assert result["platform_fee"] > 0
    assert result["minimum_safe_price"] > cost
    assert result["suggested_price"] > result["minimum_safe_price"]

def test_different_margins():
    cost = Decimal("10000")
    
    low_margin = calculate_pricing(cost, platform_margin_percent=Decimal("5.0"))
    high_margin = calculate_pricing(cost, platform_margin_percent=Decimal("20.0"))
    
    assert high_margin["minimum_safe_price"] > low_margin["minimum_safe_price"]
    assert high_margin["suggested_price"] > low_margin["suggested_price"]
