"""Decimal-safe money helpers. NEVER use float for money math."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def quantize_money(value) -> Decimal:
    return D(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_add(a, b) -> Decimal:
    return quantize_money(D(a) + D(b))


def money_sub(a, b) -> Decimal:
    return quantize_money(D(a) - D(b))


def money_mul(a, b) -> Decimal:
    return quantize_money(D(a) * D(b))


def money_percent(amount, percent) -> Decimal:
    return quantize_money(D(amount) * D(percent) / Decimal(100))
