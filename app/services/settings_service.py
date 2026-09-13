"""DB-backed settings with ENV defaults."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Setting

DEFAULTS: dict[str, str] = {
    "marketplace_commission_percent": str(settings.MARKETPLACE_COMMISSION_PERCENT),
    "donation_fee_percent": str(settings.DONATION_FEE_PERCENT),
    "service_fee_fixed": str(settings.SERVICE_FEE_FIXED),
    "service_fee_percent": str(settings.SERVICE_FEE_PERCENT),
    "site_announcement": "",
    "support_telegram": "",
    "maintenance_mode": "false",
    "donation_presets": '{"UZS": [10000, 25000, 50000, 100000, 250000, 500000], "USD": [1, 2, 5, 10, 20, 50, 100]}',
    "marketplace_categories": "accounts,items,currency,boosting,giftcards,other",
    "payment_fee_percent": "1.5",
    "promotion_price": "50000",
    "seller_premium_price": "99000",
    "exchange_rates": '{"USD": 12900}',
}


async def get_setting(db: AsyncSession, key: str) -> str:
    row = await db.get(Setting, key)
    if row and row.value is not None:
        return row.value
    return DEFAULTS.get(key, "")


async def get_float(db: AsyncSession, key: str) -> float:
    try:
        return float(await get_setting(db, key) or 0)
    except ValueError:
        return 0.0


async def set_setting(db: AsyncSession, key: str, value: str) -> Setting:
    row = await db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.flush()
    return row


async def all_settings(db: AsyncSession) -> dict[str, str]:
    rows = (await db.execute(select(Setting))).scalars().all()
    data = dict(DEFAULTS)
    for r in rows:
        data[r.key] = r.value or ""
    return data


async def donation_presets_for(db: AsyncSession, currency: str) -> list[float]:
    """Donation preset amounts for a currency.

    Source of truth: donation_presets table (admin-managed).
    Falls back to the legacy JSON setting when the table is empty.
    """
    import json as _json

    from app.models import DonationPreset

    try:
        rows = (await db.execute(select(DonationPreset)
                                 .where(DonationPreset.currency == currency, DonationPreset.is_active == True)  # noqa: E712
                                 .order_by(DonationPreset.sort_order))).scalars().all()
        if rows:
            return [float(r.amount) for r in rows][:12]
    except Exception:
        pass
    raw = await get_setting(db, "donation_presets")
    try:
        data = _json.loads(raw or "{}")
    except Exception:
        data = {}
    presets = data.get(currency) or data.get("UZS") or []
    return [float(x) for x in presets if float(x) > 0][:12]


async def marketplace_category_slugs(db: AsyncSession) -> list[str]:
    """Marketplace category slugs: marketplace_categories table first,
    legacy CSV setting as fallback."""
    from app.models import MarketplaceCategory

    try:
        rows = (await db.execute(select(MarketplaceCategory)
                                 .where(MarketplaceCategory.is_active == True)  # noqa: E712
                                 .order_by(MarketplaceCategory.sort_order))).scalars().all()
        if rows:
            return [r.slug for r in rows]
    except Exception:
        pass
    raw = await get_setting(db, "marketplace_categories")
    return [c.strip() for c in (raw or "").split(",") if c.strip()]
