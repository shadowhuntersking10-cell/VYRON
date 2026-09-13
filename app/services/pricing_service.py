"""VYRON pricing engine (server-side only).

NEVER sell at a loss: every product carries cost inputs and the engine
derives a minimum safe price + suggested price. Admins cannot save a
customer price below the safe floor unless the product is explicitly
marked as a loss-leader AND the save is explicitly confirmed.

Formula (all Decimal):
    payment_cost(price) = price * pay_pct + pay_fixed        (approx on cost base)
    cost_base           = supplier_cost + payment_cost + tax
    min_safe_price      = cost_base * (1 + minimum_margin%) + platform_fixed_fee
    suggested_price     = cost_base * (1 + platform_margin%)
"""
from __future__ import annotations

from decimal import Decimal

from app.utils.money import D, money_percent, quantize_money

DEFAULTS = {
    "payment_fee_percent": Decimal("2.0"),
    "payment_fixed_fee": Decimal("0"),
    "platform_margin_percent": Decimal("12.0"),
    "platform_fixed_fee": Decimal("0"),
    "tax_percent": Decimal("0"),
    "minimum_margin_percent": Decimal("5.0"),
    "maximum_discount_percent": Decimal("20.0"),
}


def _v(product, field: str) -> Decimal:
    raw = getattr(product, field, None)
    if raw is None:
        return DEFAULTS[field]
    return D(raw)


def quote_costs(product, price=None) -> dict:
    """Full pricing breakdown for a product at a given (or current) price."""
    cost = D(product.supplier_cost or 0)
    price = D(price if price is not None else product.selling_price or 0)
    pay_pct = _v(product, "payment_fee_percent")
    pay_fix = _v(product, "payment_fixed_fee")
    margin_pct = _v(product, "platform_margin_percent")
    margin_fix = _v(product, "platform_fixed_fee")
    tax_pct = _v(product, "tax_percent")
    min_margin = _v(product, "minimum_margin_percent")

    # Payment cost estimated on the candidate price (provider % of turnover).
    base = price if price > 0 else cost
    payment_cost = quantize_money(money_percent(base, pay_pct) + pay_fix)
    tax_cost = money_percent(base, tax_pct)
    cost_base = quantize_money(cost + payment_cost + tax_cost)
    min_safe = quantize_money(cost_base * (1 + min_margin / 100) + margin_fix)
    suggested = quantize_money(cost_base * (1 + margin_pct / 100) + margin_fix)
    profit = quantize_money(price - cost_base)
    # margin% = profit / price * 100
    margin_pct_actual = quantize_money(profit / price * 100) if price > 0 else D(0)
    below_safe = price < min_safe
    return {
        "supplier_cost": cost,
        "payment_cost": payment_cost,
        "tax_cost": tax_cost,
        "cost_base": cost_base,
        "minimum_safe_price": min_safe,
        "suggested_price": suggested,
        "current_price": price,
        "estimated_profit": profit,
        "profit_margin_percent": margin_pct_actual,
        "below_safe": below_safe,
        "loss_leader_allowed": bool(getattr(product, "loss_leader_allowed", False)),
        "currency": getattr(product, "currency", "UZS"),
    }


class UnsafePriceError(ValueError):
    """Raised when an admin price would generate a loss."""


def validate_price(product, new_price, *, confirmed: bool = False) -> dict:
    """Validate a candidate customer price. Returns the quote.

    Raises UnsafePriceError unless the price is safe, or the product is a
    confirmed loss-leader save.
    """
    q = quote_costs(product, new_price)
    if q["below_safe"]:
        if not (q["loss_leader_allowed"] and confirmed):
            raise UnsafePriceError(
                'WARNING: "This price may generate a loss." '
                f"Minimum safe price is {q['minimum_safe_price']} {q['currency']}."
            )
    return q


def apply_pricing(product, data: dict) -> None:
    """Apply pricing input fields from admin forms onto a product/variant."""
    for field in (
        "payment_fee_percent", "payment_fixed_fee", "platform_margin_percent",
        "platform_fixed_fee", "tax_percent", "minimum_margin_percent",
        "maximum_discount_percent", "loss_leader_allowed",
    ):
        if field in data and data[field] is not None:
            setattr(product, field, data[field])
