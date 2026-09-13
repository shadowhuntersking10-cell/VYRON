import pytest
from app.utils.security import hash_password, verify_password, validate_password_strength, verify_telegram_init_data
from app.utils.helpers import validate_username, validate_email, calculate_pricing

def test_password_hashing():
    pwd = "Test123!@#"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed)
    assert not verify_password("wrong", hashed)

def test_password_strength():
    valid, msg = validate_password_strength("short")
    assert not valid
    
    valid, msg = validate_password_strength("ValidPass123!")
    assert valid

def test_username_validation():
    valid, msg = validate_username("ab")
    assert not valid
    
    valid, msg = validate_username("valid_user123")
    assert valid
    
    valid, msg = validate_username("123invalid")
    assert not valid

def test_email_validation():
    assert validate_email("test@example.com")
    assert not validate_email("invalid-email")

def test_pricing_engine():
    from decimal import Decimal
    pricing = calculate_pricing(Decimal("40000"))
    
    assert pricing["supplier_cost"] == Decimal("40000.00")
    assert pricing["minimum_safe_price"] > Decimal("40000")
    assert pricing["suggested_price"] >= pricing["minimum_safe_price"]
    assert pricing["expected_profit"] > 0

def test_pricing_loss_protection():
    from decimal import Decimal
    from app.services.pricing import PricingService
    
    # Customer price below safe price should be flagged as loss
    result = PricingService.validate_price(Decimal("40000"), Decimal("30000"))
    assert result["is_loss"] == True
    assert result["can_save"] == False
    
    # Valid price
    result = PricingService.validate_price(Decimal("40000"), Decimal("50000"))
    assert result["is_loss"] == False
    assert result["can_save"] == True

def test_telegram_validation_missing():
    valid, data, error = verify_telegram_init_data("", "fake_token")
    assert not valid

def test_order_number_generation():
    from app.utils.security import generate_order_number, generate_idempotency_key
    num1 = generate_order_number()
    num2 = generate_order_number()
    assert num1 != num2
    assert num1.startswith("VYRON-")
    
    key1 = generate_idempotency_key()
    key2 = generate_idempotency_key()
    assert key1 != key2

def test_donation_fees():
    from decimal import Decimal
    from app.services.pricing import PricingService
    
    result = PricingService.calculate_donation_fees(Decimal("100000"), Decimal("5"))
    assert result["gross"] == Decimal("100000.00")
    assert result["fee"] == Decimal("5000.00")
    assert result["net"] == Decimal("95000.00")

def test_marketplace_commission():
    from decimal import Decimal
    from app.services.pricing import PricingService
    
    result = PricingService.calculate_marketplace_commission(Decimal("100000"), Decimal("10"))
    assert result["gross"] == Decimal("100000.00")
    assert result["commission"] == Decimal("10000.00")
    assert result["seller_earnings"] == Decimal("90000.00")
