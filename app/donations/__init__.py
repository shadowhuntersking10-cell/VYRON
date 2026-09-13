"""Donation helpers."""
from __future__ import annotations

from decimal import Decimal

from app.services.pricing import q


def fee_breakdown(amount, fee_percent) -> dict:
    amount = q(amount)
    fee = (amount * q(fee_percent) / 100).quantize(Decimal("0.01"))
    return {"amount": amount, "fee": fee, "net": (amount - fee).quantize(Decimal("0.01"))}
