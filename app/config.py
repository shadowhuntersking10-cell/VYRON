"""Central application configuration (Pydantic Settings)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- App ----
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    APP_NAME: str = "VYRON"
    APP_SECRET: str = "dev-secret-change-me-please-32-chars-min"
    APP_BASE_URL: str = "http://localhost:8000"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    DEFAULT_LANG: str = "uz"
    DEFAULT_CURRENCY: str = "UZS"

    # ---- MySQL ----
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = "vyron"
    MYSQL_USER: str = "vyron"
    MYSQL_PASSWORD: str = ""
    DATABASE_URL: str = ""

    # ---- Redis ----
    REDIS_URL: str = ""

    # ---- Sessions ----
    SESSION_COOKIE_NAME: str = "vyron_session"
    SESSION_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    RATE_LIMIT_PER_MINUTE: int = 60

    # ---- Telegram ----
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""
    TELEGRAM_WEBAPP_URL: str = ""
    ADMIN_TELEGRAM_IDS: str = ""
    TELEGRAM_AUTH_MAX_AGE_SECONDS: int = 86400

    # ---- Payme ----
    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET_KEY: str = ""
    PAYME_TEST_MODE: bool = True

    # ---- Click ----
    CLICK_MERCHANT_ID: str = ""
    CLICK_SERVICE_ID: str = ""
    CLICK_SECRET_KEY: str = ""
    CLICK_TEST_MODE: bool = True

    # ---- Stripe ----
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_TEST_MODE: bool = True

    # ---- Suppliers ----
    SUPPLIER_DEFAULT: str = "manual"
    SUPPLIER_API_URL: str = ""
    SUPPLIER_API_KEY: str = ""
    SUPPLIER_API_SECRET: str = ""
    SUPPLIER_MERCHANT_ID: str = ""

    # ---- SMTP ----
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    # ---- Storage ----
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"
    STORAGE_MAX_FILE_MB: int = 5
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = ""

    # ---- Revenue defaults ----
    MARKETPLACE_COMMISSION_PERCENT: float = 10.0
    DONATION_FEE_PERCENT: float = 5.0
    SERVICE_FEE_FIXED: float = 0.0
    SERVICE_FEE_PERCENT: float = 0.0

    # ---- Seed ----
    SEED_DEMO_DATA: bool = True
    ADMIN_EMAIL: str = "admin@vyron.local"
    ADMIN_PASSWORD: str = "Admin12345!"

    # ---- paths ----
    BASE_DIR: Path = Field(default=BASE_DIR, exclude=True)

    @field_validator("ADMIN_TELEGRAM_IDS", mode="before")
    @classmethod
    def _ids_to_str(cls, v):  # allow list in code
        if isinstance(v, (list, tuple, set)):
            return ",".join(str(x) for x in v)
        return v or ""

    @property
    def admin_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in (self.ADMIN_TELEGRAM_IDS or "").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def effective_database_url(self) -> str:
        """DATABASE_URL wins; otherwise build MySQL URL from parts."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.MYSQL_PASSWORD:
            return (
                f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
                f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            )
        # Dev fallback: local sqlite so `python main.py` always boots.
        return "sqlite+aiosqlite:///./vyron_dev.db"

    @property
    def using_mysql(self) -> bool:
        return self.effective_database_url.startswith("mysql")

    @property
    def payme_configured(self) -> bool:
        return bool(self.PAYME_MERCHANT_ID and self.PAYME_SECRET_KEY)

    @property
    def click_configured(self) -> bool:
        return bool(self.CLICK_MERCHANT_ID and self.CLICK_SECRET_KEY)

    @property
    def stripe_configured(self) -> bool:
        return bool(self.STRIPE_SECRET_KEY)

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN)

    @property
    def supplier_configured(self) -> bool:
        return bool(self.SUPPLIER_API_URL and self.SUPPLIER_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
