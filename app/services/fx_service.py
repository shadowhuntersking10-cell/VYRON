"""Server-side multi-currency: rates, conversion, order snapshots.

Base books are kept in UZS. Rates are admin-configurable
(`exchange_rates` setting: {"USD": 12900, ...} meaning 1 USD = X UZS).
Never convert money in frontend JavaScript.
"""
from __future__ import annotations

import json as _json
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import settings_service
from app.utils.helpers import utcnow
from app.utils.money import D, quantize_money

BASE_CURRENCY = "UZS"
SUPPORTED = ("UZS", "USD")


async def get_rates(db: AsyncSession) -> dict[str, Decimal]:
    raw = await settings_service.get_setting(db, "exchange_rates")
    try:
        data = _json.loads(raw or "{}")
    except Exception:
        data = {}
    rates = {BASE_CURRENCY: D(1)}
    for code, value in data.items():
        try:
            if D(value) > 0:
                rates[str(code).upper()] = D(value)
        except Exception:
            continue
    rates.setdefault("USD", D(12900))
    return rates


async def convert(db: AsyncSession, amount, from_currency: str, to_currency: str) -> Decimal:
    """Convert amount between currencies using server-side rates."""
    from_currency = (from_currency or BASE_CURRENCY).upper()
    to_currency = (to_currency or BASE_CURRENCY).upper()
    if from_currency == to_currency:
        return quantize_money(amount)
    rates = await get_rates(db)
    if from_currency not in rates or to_currency not in rates:
        raise ValueError(f"fx_unsupported:{from_currency}->{to_currency}")
    in_base = D(amount) * rates[from_currency]
    return quantize_money(in_base / rates[to_currency])


async def snapshot_for_order(db: AsyncSession, currency: str) -> dict:
    """Build the FX snapshot stored on the order (rate vs base currency)."""
    currency = (currency or BASE_CURRENCY).upper()
    rates = await get_rates(db)
    return {
        "fx_base_currency": BASE_CURRENCY,
        "fx_rate": rates.get(currency, D(1)),
        "fx_quoted_at": utcnow(),
    }


async def to_base(db: AsyncSession, amount, currency: str) -> Decimal:
    return await convert(db, amount, currency, BASE_CURRENCY)
