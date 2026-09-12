"""Platform settings service — runtime-configurable business parameters.

All commissions/fees/limits are stored in `platform_settings` and seeded from
environment defaults on first boot. Admin changes take effect immediately
(cache invalidation).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.config import settings as env_settings
from vyron.db.models import PlatformSetting, settings_cache
from vyron.money import to_money


def ensure_defaults(db: DbSession) -> int:
    """Insert missing default settings (env-derived). Idempotent."""
    env_defaults = {
        "marketplace_commission_pct": str(env_settings.marketplace_commission_pct),
        "donation_fee_pct": str(env_settings.donation_fee_pct),
        "donation_fee_fixed": str(env_settings.donation_fee_fixed),
        "service_fee_pct": str(env_settings.service_fee_pct),
        "seller_holding_period_hours": str(env_settings.seller_holding_period_hours),
        "min_payout_amount": str(env_settings.min_payout_amount),
        "promoted_listing_price": str(env_settings.promoted_listing_price),
        "featured_listing_price": str(env_settings.featured_listing_price),
    }
    from vyron.db.models.platform import DEFAULT_SETTINGS

    merged = {**DEFAULT_SETTINGS, **env_defaults}
    created = 0
    existing = {row.key for row in db.query(PlatformSetting.key).all()}
    for key, value in merged.items():
        if key not in existing:
            db.add(PlatformSetting(key=key, value=str(value)))
            created += 1
    if created:
        db.commit()
        settings_cache.invalidate()
    return created


def get_setting(db: DbSession, key: str, default: Optional[str] = None) -> str:
    return settings_cache.get_str(db, key, default)


def get_decimal_setting(db: DbSession, key: str, default: str = "0") -> Decimal:
    return settings_cache.get_decimal(db, key, default)


def get_int_setting(db: DbSession, key: str, default: int = 0) -> int:
    return settings_cache.get_int(db, key, default)


def get_bool_setting(db: DbSession, key: str, default: bool = False) -> bool:
    return settings_cache.get_bool(db, key, default)


def set_setting(db: DbSession, key: str, value: Any, updated_by: Optional[str] = None) -> PlatformSetting:
    row = db.get(PlatformSetting, key)
    if row is None:
        row = PlatformSetting(key=key, value=str(value), updated_by=updated_by)
        db.add(row)
    else:
        row.value = str(value)
        row.updated_by = updated_by
    db.commit()
    settings_cache.invalidate()
    return row


def all_settings(db: DbSession) -> Dict[str, Any]:
    rows = db.query(PlatformSetting).order_by(PlatformSetting.key).all()
    return {row.key: row.value for row in rows}


# --- Business-parameter shortcuts -------------------------------------------------
def marketplace_commission_pct(db: DbSession) -> Decimal:
    return get_decimal_setting(db, "marketplace_commission_pct", str(env_settings.marketplace_commission_pct))


def donation_fee(db: DbSession, gross_amount: Decimal) -> Decimal:
    pct = get_decimal_setting(db, "donation_fee_pct", str(env_settings.donation_fee_pct))
    fixed = get_decimal_setting(db, "donation_fee_fixed", str(env_settings.donation_fee_fixed))
    from vyron.money import pct_of, sum_money

    return sum_money(pct_of(gross_amount, pct), fixed)


def service_fee(db: DbSession, subtotal: Decimal) -> Decimal:
    from vyron.money import pct_of

    pct = get_decimal_setting(db, "service_fee_pct", str(env_settings.service_fee_pct))
    return pct_of(subtotal, pct)


def holding_period_hours(db: DbSession) -> int:
    return get_int_setting(db, "seller_holding_period_hours", env_settings.seller_holding_period_hours)


def min_payout_amount(db: DbSession) -> Decimal:
    return get_decimal_setting(db, "min_payout_amount", str(env_settings.min_payout_amount))


def promotion_price(db: DbSession, kind: str) -> Decimal:
    key = {
        "FEATURED": "featured_listing_price",
        "HOMEPAGE": "homepage_promotion_price",
        "SEARCH": "search_promotion_price",
        "CATEGORY": "promoted_listing_price",
    }.get(kind.upper(), "promoted_listing_price")
    return get_decimal_setting(db, key, str(env_settings.promoted_listing_price))


# --- admin management --------------------------------------------------------------------
EDITABLE_SETTING_KEYS = {
    "marketplace_commission_pct",
    "donation_fee_pct",
    "donation_fee_fixed",
    "service_fee_pct",
    "seller_holding_period_hours",
    "min_payout_amount",
    "promoted_listing_price",
    "featured_listing_price",
    "homepage_promotion_price",
    "search_promotion_price",
    "promotion_default_days",
    "max_open_tickets_per_user",
    "maintenance_mode",
    "support_telegram",
    "support_email",
}


def admin_snapshot(db: DbSession) -> Dict[str, Any]:
    values = all_settings(db)
    for key in EDITABLE_SETTING_KEYS:
        values.setdefault(key, "")
    return {"settings": values, "editable_keys": sorted(EDITABLE_SETTING_KEYS)}


def admin_update(db: DbSession, admin, payload: Dict[str, Any]) -> Dict[str, Any]:
    from vyron.services import audit_service

    changed: Dict[str, str] = {}
    for key, value in (payload.get("settings") or payload).items():
        if key not in EDITABLE_SETTING_KEYS:
            continue  # unknown/protected keys are ignored, never written
        before = get_setting(db, key, "")
        new_value = str(value)
        if new_value == before:
            continue
        # sanity checks for numeric business parameters
        if key.endswith("_pct"):
            number = to_money(new_value or "0")
            if number < 0 or number > 100:
                from vyron.errors import ValidationError

                raise ValidationError(f"{key} must be between 0 and 100.", code="SETTING_INVALID")
        set_setting(db, key, new_value, updated_by=admin.username)
        changed[key] = new_value
    if changed:
        audit_service.record_admin_action(db, admin, "settings.updated", data={"changed": changed})
    return admin_snapshot(db)
