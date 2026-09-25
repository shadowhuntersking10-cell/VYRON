"""VYRON application configuration.

Secrets are read from the environment (optionally via a local .env file).
Nothing secret is ever written to logs, API responses or the database.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Does not override real env."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.app_env: str = os.environ.get("APP_ENV", "production")
        self.app_debug: bool = os.environ.get("APP_DEBUG", "false").lower() == "true"
        self.public_base_url: str = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
        self.webapp_url: str = os.environ.get("WEBAPP_URL", self.public_base_url).rstrip("/")
        self.session_secret: str = os.environ.get("SESSION_SECRET", "")
        self.database_url: str = os.environ.get(
            "DATABASE_URL",
            "mysql+pymysql://vyron:vyron_password@127.0.0.1:3306/vyron",
        )
        self.database_fallback_sqlite: bool = (
            os.environ.get("DATABASE_FALLBACK_SQLITE", "true").lower() == "true"
        )
        self.payerpin_api_key: str = os.environ.get("PAYERPIN_API_KEY", "")
        self.payerpin_base_url: str = os.environ.get(
            "PAYERPIN_BASE_URL", "https://api.payerpin.uz"
        ).rstrip("/")
        self.payment_provider: str = os.environ.get("PAYMENT_PROVIDER", "").strip().lower()
        self.payment_api_key: str = os.environ.get("PAYMENT_API_KEY", "")
        self.payment_secret: str = os.environ.get("PAYMENT_SECRET", "")
        self.payment_webhook_secret: str = os.environ.get("PAYMENT_WEBHOOK_SECRET", "")
        self.payment_currency: str = os.environ.get("PAYMENT_CURRENCY", "UZS").upper()
        self.telegram_bot_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_admin_ids: list[int] = self._parse_admin_ids(
            os.environ.get("TELEGRAM_ADMIN_IDS", "")
        )
        self.host: str = os.environ.get("HOST", "0.0.0.0")
        self.port: int = int(os.environ.get("PORT", "8000"))
        self.log_level: str = os.environ.get("LOG_LEVEL", "INFO").upper()
        self.fulfillment_worker_enabled: bool = (
            os.environ.get("FULFILLMENT_WORKER_ENABLED", "true").lower() == "true"
        )
        self.fulfillment_poll_seconds: int = int(
            os.environ.get("FULFILLMENT_POLL_SECONDS", "5")
        )
        self.catalog_sync_interval_minutes: int = int(
            os.environ.get("CATALOG_SYNC_INTERVAL_MINUTES", "60")
        )
        self.rate_limit_enabled: bool = (
            os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
        )

    @staticmethod
    def _parse_admin_ids(raw: str) -> list[int]:
        ids: list[int] = []
        for part in raw.replace(";", ",").replace(" ", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return sorted(set(ids))

    # ---- secret-safe helpers -------------------------------------------------
    def payerpin_configured(self) -> bool:
        return bool(self.payerpin_api_key)

    def payment_configured(self) -> bool:
        return bool(self.payment_provider and self.payment_webhook_secret)

    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    def require_session_secret(self) -> str:
        if self.session_secret and len(self.session_secret) >= 16:
            return self.session_secret
        if self.app_env == "production":
            raise RuntimeError(
                "SESSION_SECRET is not configured. Set a long random SESSION_SECRET "
                "in the environment (.env) before starting VYRON in production."
            )
        # Deterministic development-only fallback (never used in production).
        return "dev-only-insecure-session-secret-change-me"

    def safe_summary(self) -> dict:
        """Configuration state WITHOUT any secret values."""
        return {
            "app_env": self.app_env,
            "database": self.database_url.split("://", 1)[0] if self.database_url else None,
            "payerpin_configured": self.payerpin_configured(),
            "payerpin_base_url": self.payerpin_base_url,
            "payment_provider": self.payment_provider or None,
            "payment_configured": self.payment_configured(),
            "telegram_configured": self.telegram_configured(),
            "telegram_admins_configured": bool(self.telegram_admin_ids),
            "rate_limit_enabled": self.rate_limit_enabled,
            "fulfillment_worker_enabled": self.fulfillment_worker_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
