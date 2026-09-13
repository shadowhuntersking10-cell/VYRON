from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
import re

def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def quantize_money(value: Decimal) -> Decimal:
    return to_decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def calculate_pricing(
    supplier_cost: Decimal,
    payment_fee_percent: Decimal = Decimal("2.0"),
    payment_fixed_fee: Decimal = Decimal("500"),
    safety_buffer_percent: Decimal = Decimal("2.0"),
    platform_margin_percent: Decimal = Decimal("10.0"),
    commission_percent: Decimal = Decimal("0.0"),
    tax_percent: Decimal = Decimal("0.0")
) -> Dict[str, Decimal]:
    """
    Core pricing engine - protects from losses
    """
    supplier_cost = to_decimal(supplier_cost)
    payment_fee_percent = to_decimal(payment_fee_percent)
    payment_fixed_fee = to_decimal(payment_fixed_fee)
    safety_buffer_percent = to_decimal(safety_buffer_percent)
    platform_margin_percent = to_decimal(platform_margin_percent)
    commission_percent = to_decimal(commission_percent)
    tax_percent = to_decimal(tax_percent)

    # Payment fee = supplier_cost * payment_fee_percent + fixed
    payment_fee = (supplier_cost * payment_fee_percent / Decimal("100")) + payment_fixed_fee

    # Safety buffer
    safety_buffer = supplier_cost * safety_buffer_percent / Decimal("100")

    # Base cost including fees and buffer
    base_cost = supplier_cost + payment_fee + safety_buffer

    # Platform fee / margin
    platform_fee = base_cost * platform_margin_percent / Decimal("100")

    # Commission
    commission = base_cost * commission_percent / Decimal("100")

    # Tax
    tax = base_cost * tax_percent / Decimal("100")

    # Minimum safe price = base_cost + platform_fee + commission + tax
    minimum_safe_price = base_cost + platform_fee + commission + tax

    # Suggested price adds extra 5% for profit optimization
    suggested_price = minimum_safe_price * Decimal("1.05")

    # Round
    minimum_safe_price = quantize_money(minimum_safe_price)
    suggested_price = quantize_money(suggested_price)
    payment_fee = quantize_money(payment_fee)
    platform_fee = quantize_money(platform_fee)
    safety_buffer = quantize_money(safety_buffer)

    expected_profit_at_suggested = quantize_money(suggested_price - supplier_cost - payment_fee - safety_buffer)

    return {
        "supplier_cost": quantize_money(supplier_cost),
        "payment_fee": payment_fee,
        "payment_fee_percent": payment_fee_percent,
        "payment_fixed_fee": quantize_money(payment_fixed_fee),
        "safety_buffer": safety_buffer,
        "safety_buffer_percent": safety_buffer_percent,
        "platform_fee": platform_fee,
        "platform_margin_percent": platform_margin_percent,
        "commission": quantize_money(commission),
        "tax": quantize_money(tax),
        "minimum_safe_price": minimum_safe_price,
        "suggested_price": suggested_price,
        "expected_profit": expected_profit_at_suggested,
        "base_cost": quantize_money(base_cost),
    }

def validate_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None

def validate_username(username: str) -> tuple[bool, str]:
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 30:
        return False, "Username must be less than 30 characters"
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username can only contain letters, numbers and underscore"
    if username[0].isdigit():
        return False, "Username cannot start with a number"
    return True, "OK"

def format_money(amount: Decimal, currency: str = "UZS") -> str:
    amount = quantize_money(amount)
    if currency == "UZS":
        return f"{amount:,.0f} {currency}"
    return f"{amount:,.2f} {currency}"

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    text = re.sub(r"-+", "-", text)
    return text[:100]
