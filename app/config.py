"""Central application configuration (Pydantic Settings, env-based)."""
from __future__ import annotations

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    APP_NAME: str = "VYRON"
    APP_SECRET: str = "change-me-in-production"
    BASE_URL: str = "http://localhost:8000"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    MYSQL_HOST: str = ""
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str = ""
    MYSQL_USER: str = ""
    MYSQL_PASSWORD: str = ""
    DATABASE_URL: str = ""

    REDIS_URL: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBAPP_URL: str = ""
    ADMIN_TELEGRAM_IDS: str = ""

    SALES_ENABLED: bool = True
    SUPPLIER_ORDERS_ENABLED: bool = True
    PAYMENTS_ENABLED: bool = True
    LOSS_SELLING: bool = False

    PAYMENT_FEE_PERCENT: float = 2.0
    PAYMENT_FEE_FIXED: float = 500.0
    SAFETY_BUFFER_PERCENT: float = 2.0
    PLATFORM_MARGIN_PERCENT: float = 10.0
    PLATFORM_FEE_PERCENT: float = 5.0
    MINIMUM_MARGIN_PERCENT: float = 5.0
    MAXIMUM_DISCOUNT_PERCENT: float = 30.0
    MARKETPLACE_COMMISSION_PERCENT: float = 10.0
    DONATION_FEE_PERCENT: float = 5.0
    DEFAULT_CURRENCY: str = "UZS"

    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET: str = ""
    PAYME_ENDPOINT: str = ""
    CLICK_MERCHANT_ID: str = ""
    CLICK_SERVICE_ID: str = ""
    CLICK_SECRET: str = ""
    CLICK_ENDPOINT: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    SUPPLIER_API_URL: str = ""
    SUPPLIER_API_KEY: str = ""
    SUPPLIER_AUTO_PRICE_UPDATE: bool = False

    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = ""
    STORAGE_SECRET_KEY: str = ""
    STORAGE_BUCKET: str = ""
    MEDIA_DIR: str = "static/uploads"
    MAX_UPLOAD_MB: int = 5

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@vyron.example.com"

    SESSION_COOKIE: str = "vyron_session"
    SESSION_TTL_HOURS: int = 72
    CSRF_COOKIE: str = "vyron_csrf"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def admin_telegram_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in (self.ADMIN_TELEGRAM_IDS or "").replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    def effective_database_url(self) -> tuple[str, bool]:
        """Return (url, is_mysql). Falls back to local SQLite in non-production."""
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            return url, url.startswith("mysql")
        if self.MYSQL_HOST and self.MYSQL_DATABASE and self.MYSQL_USER:
            url = (
                f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
                f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"
            )
            return url, True
        return "sqlite:///./dev.db", False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
