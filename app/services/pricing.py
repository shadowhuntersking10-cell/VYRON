"""Pricing engine: loss protection, minimum safe price, suggested price.

All money uses Decimal. Never calculate financial values in frontend only.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

Q = Decimal("0.01")


def q(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q, rounding=ROUND_HALF_UP)


class PriceQuote(dict):
    pass


def quote(
    supplier_cost,
    payment_fee_percent=0,
    payment_fee_fixed=0,
    safety_buffer_percent=0,
    platform_margin_percent=10,
    minimum_margin_percent=5,
    platform_fee_percent=0,
    current_price=0,
    new_price=None,
) -> dict:
    c = q(supplier_cost)
    p = q(payment_fee_percent) / 100
    f = q(payment_fee_fixed)
    b = q(safety_buffer_percent) / 100
    m = q(platform_margin_percent) / 100
    mm = q(minimum_margin_percent) / 100
    pf = q(platform_fee_percent) / 100

    variable = p + b + pf
    if variable >= 1:
        variable = Decimal("0.99")
    base = (c + f) / (1 - variable)
    minimum_safe = (base * (1 + mm)).quantize(Q, rounding=ROUND_HALF_UP)
    suggested = (base * (1 + m)).quantize(Q, rounding=ROUND_HALF_UP)

    price = q(new_price) if new_price is not None else q(current_price)
    payment_fee = (price * p + f).quantize(Q, rounding=ROUND_HALF_UP)
    platform_fee = (price * pf).quantize(Q, rounding=ROUND_HALF_UP)
    buffer_amt = (price * b).quantize(Q, rounding=ROUND_HALF_UP)
    profit = (price - payment_fee - platform_fee - buffer_amt - c).quantize(Q, rounding=ROUND_HALF_UP)
    margin = (profit / price * 100).quantize(Q) if price > 0 else Decimal("0")
    max_discount = max(Decimal("0"), (price - minimum_safe)).quantize(Q)

    return {
        "supplier_cost": c,
        "payment_fee": payment_fee,
        "platform_fee": platform_fee,
        "safety_buffer": buffer_amt,
        "minimum_safe_price": minimum_safe,
        "suggested_price": suggested,
        "current_price": q(current_price),
        "new_price": q(new_price) if new_price is not None else None,
        "expected_profit": profit,
        "expected_margin_percent": margin,
        "max_safe_discount": max_discount,
        "blocked": False,
        "warning": "",
    }


def enforce_price(new_price, quote_result: dict, allow_override: bool = False) -> tuple[bool, str]:
    """Returns (allowed, warning_or_error). Blocks loss sales by default."""
    new_price = q(new_price)
    min_safe = quote_result["minimum_safe_price"]
    profit = quote_result["expected_profit"]
    if new_price < min_safe or profit < 0:
        if allow_override:
            return True, "override_below_minimum"
        return False, "price_below_minimum"
    if profit < 0:
        return False, "price_would_lose_money"
    return True, ""


def product_fees(product, settings_obj) -> dict:
    """Merge product-level fee overrides with global settings."""
    def pick(product_val, global_val):
        pv = q(product_val)
        return pv if pv > 0 else q(global_val)

    return {
        "payment_fee_percent": pick(product.payment_fee_percent, settings_obj.PAYMENT_FEE_PERCENT),
        "payment_fee_fixed": q(settings_obj.PAYMENT_FEE_FIXED),
        "safety_buffer_percent": q(settings_obj.SAFETY_BUFFER_PERCENT),
        "platform_margin_percent": q(product.markup_percent) if q(product.markup_percent) > 0 else q(settings_obj.PLATFORM_MARGIN_PERCENT),
        "minimum_margin_percent": pick(product.minimum_margin_percent, settings_obj.MINIMUM_MARGIN_PERCENT),
        "platform_fee_percent": pick(product.platform_fee_percent, settings_obj.PLATFORM_FEE_PERCENT),
    }


def quote_for_product(product, settings_obj, new_price=None) -> dict:
    fees = product_fees(product, settings_obj)
    return quote(
        product.supplier_cost,
        current_price=product.customer_price,
        new_price=new_price,
        **fees,
    )
