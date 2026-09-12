"""Runtime-configurable platform settings (fees, commissions, limits).

Everything the business can tune lives here — nothing is hardcoded:
marketplace commission, donation fee, service fee, holding period,
minimum payout, promotion pricing, subscription plans, maintenance flags.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vyron.db.base import Base, UTCDateTime, utcnow
from vyron.money import to_money

# Canonical setting keys and their defaults (mirrored from .env at first boot).
DEFAULT_SETTINGS: dict[str, Any] = {
    "marketplace_commission_pct": "10.0",
    "donation_fee_pct": "5.0",
    "donation_fee_fixed": "0.00",
    "service_fee_pct": "0.0",
    "seller_holding_period_hours": "72",
    "min_payout_amount": "10.00",
    "promoted_listing_price": "5.00",
    "featured_listing_price": "10.00",
    "homepage_promotion_price": "15.00",
    "search_promotion_price": "3.00",
    "promotion_default_days": "7",
    "max_open_tickets_per_user": "5",
    "maintenance_mode": "0",
    "support_telegram": "",
    "support_email": "support@vyron.app",
}


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, onupdate=utcnow)

    @staticmethod
    def parse(raw: str) -> Any:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw


class SettingCache:
    """Tiny in-process cache with explicit invalidation after admin writes."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._loaded = False

    def load(self, db) -> None:
        rows = db.query(PlatformSetting).all()
        self._values = {row.key: row.value for row in rows}
        self._loaded = True

    def invalidate(self) -> None:
        self._loaded = False
        self._values = {}

    def get_str(self, db, key: str, default: Optional[str] = None) -> str:
        if not self._loaded:
            self.load(db)
        if key in self._values:
            return self._values[key]
        if default is not None:
            return default
        return str(DEFAULT_SETTINGS.get(key, ""))

    def get_decimal(self, db, key: str, default: str = "0") -> Decimal:
        raw = self.get_str(db, key, default)
        try:
            return to_money(raw)
        except (InvalidOperation, ValueError):
            return to_money(default)

    def get_int(self, db, key: str, default: int = 0) -> int:
        raw = self.get_str(db, key, str(default))
        try:
            return int(float(raw))
        except (ValueError, TypeError):
            return default

    def get_bool(self, db, key: str, default: bool = False) -> bool:
        raw = self.get_str(db, key, "1" if default else "0")
        return raw.strip().lower() in {"1", "true", "yes", "on"}


settings_cache = SettingCache()
