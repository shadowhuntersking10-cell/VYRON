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
