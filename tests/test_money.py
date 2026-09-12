"""Money handling: exact Decimal arithmetic (ROUND_HALF_UP), strict input validation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pytest


def test_to_money_quantizes_half_up():
    from vyron.money import to_money

    assert to_money("1.005") == Decimal("1.01")
    assert to_money(3) == Decimal("3.00")
    assert to_money("9.999") == Decimal("10.00")
    assert to_money(Decimal("2.345")) == Decimal("2.35")


def test_to_money_rejects_garbage():
    from vyron.money import to_money

    with pytest.raises(InvalidOperation):
        to_money(None)
    with pytest.raises(InvalidOperation):
        to_money("abc")


def test_money_is_decimal_not_float():
    from vyron.money import to_money

    assert to_money("0.1") + to_money("0.2") == Decimal("0.30")


def test_pct_of_and_sum_money():
    from vyron.money import pct_of, sum_money

    assert pct_of("100.00", "10") == Decimal("10.00")
    assert pct_of("33.33", "15") == Decimal("5.00")
    assert sum_money("1.10", "2.20", None, "3.30") == Decimal("6.60")


def test_format_money():
    from vyron.money import format_money

    assert format_money("1234.5", "USD") == "$1,234.50"
    assert "so'm" in format_money("50000", "UZS")
