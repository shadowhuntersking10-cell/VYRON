"""Exact decimal money arithmetic.

RULE: JavaScript/Python floating point is NEVER used for financial values.
All amounts are `decimal.Decimal`, quantized to 2 decimal places (cents).
MySQL columns are DECIMAL — exact on both sides.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Union

CENTS = Decimal("0.01")
ZERO = Decimal("0.00")

Numeric = Union[Decimal, int, str]


def to_money(value: Any) -> Decimal:
    """Convert input into an exact Decimal money value (2dp, ROUND_HALF_UP).

    Accepts Decimal/int/str. Floats are converted through their string repr to
    avoid binary artifacts, but callers should prefer strings/Decimals.
    """
    if value is None:
        raise InvalidOperation("Cannot convert None to money")
    if isinstance(value, float):
        value = repr(value)
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    if not d.is_finite():
        raise InvalidOperation("Money value must be finite")
    return d.quantize(CENTS, rounding=ROUND_HALF_UP)


def money(value: Any) -> Decimal:
    """Alias of to_money that clamps negatives to zero for fee-like usages is NOT done;
    use to_money everywhere; negatives are legal (refunds, ledger debits)."""
    return to_money(value)


def sum_money(*values: Any) -> Decimal:
    total = ZERO
    for v in values:
        total += to_money(v or 0)
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


def pct_of(amount: Any, pct: Any) -> Decimal:
    """amount * pct / 100 with exact rounding (HALF_UP to cents)."""
    return (to_money(amount) * to_money(pct) / Decimal(100)).quantize(CENTS, rounding=ROUND_HALF_UP)


def format_money(amount: Any, currency: str = "USD") -> str:
    symbol = {"USD": "$", "UZS": "so'm", "EUR": "€", "RUB": "₽"}.get(currency.upper(), currency)
    value = to_money(amount)
    if currency.upper() == "UZS":
        return f"{value.quantize(Decimal('1')):f} {symbol}"
    return f"{symbol}{value:,.2f}"


def decimal_to_str(value: Any) -> str:
    return str(to_money(value))
