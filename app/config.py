from __future__ import annotations
import os
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = Field(default="development")
    APP_SECRET: str = Field(default="dev-secret-key-change-in-production-min-32-chars-long")
    APP_NAME: str = Field(default="VYRON")
    APP_URL: str = Field(default="http://localhost:8000")
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000)

    # Database
    MYSQL_HOST: str = Field(default="localhost")
    MYSQL_PORT: int = Field(default=3306)
    MYSQL_DATABASE: str = Field(default="vyron")
    MYSQL_USER: str = Field(default="vyron")
    MYSQL_PASSWORD: str = Field(default="vyron_password")
    DATABASE_URL: Optional[str] = Field(default=None)

    # Redis
    REDIS_URL: Optional[str] = Field(default=None)

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None)
    TELEGRAM_WEBAPP_URL: Optional[str] = Field(default=None)
    TELEGRAM_BOT_USERNAME: Optional[str] = Field(default=None)
    ADMIN_TELEGRAM_IDS: str = Field(default="")

    # Payments
    PAYME_MERCHANT_ID: Optional[str] = Field(default=None)
    PAYME_SECRET: Optional[str] = Field(default=None)
    PAYME_ENDPOINT: str = Field(default="https://checkout.paycom.uz/api")

    CLICK_MERCHANT_ID: Optional[str] = Field(default=None)
    CLICK_SERVICE_ID: Optional[str] = Field(default=None)
    CLICK_SECRET: Optional[str] = Field(default=None)
    CLICK_ENDPOINT: str = Field(default="https://api.click.uz/v2/merchant")

    STRIPE_SECRET_KEY: Optional[str] = Field(default=None)
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None)
    STRIPE_PUBLISHABLE_KEY: Optional[str] = Field(default=None)

    # Supplier
    SUPPLIER_API_URL: Optional[str] = Field(default=None)
    SUPPLIER_API_KEY: Optional[str] = Field(default=None)
    SUPPLIER_ENABLED: bool = Field(default=False)

    # Storage
    STORAGE_ENDPOINT: Optional[str] = Field(default=None)
    STORAGE_ACCESS_KEY: Optional[str] = Field(default=None)
    STORAGE_SECRET_KEY: Optional[str] = Field(default=None)
    STORAGE_BUCKET: str = Field(default="vyron-media")
    STORAGE_REGION: str = Field(default="us-east-1")
    STORAGE_PUBLIC_URL: Optional[str] = Field(default=None)

    # SMTP
    SMTP_HOST: Optional[str] = Field(default=None)
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    SMTP_FROM: str = Field(default="noreply@vyron.uz")
    SMTP_TLS: bool = Field(default=True)

    # Security
    SESSION_SECRET: str = Field(default="dev-session-secret-change-in-production-32-chars")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRE_MINUTES: int = Field(default=10080)

    # Business Safety
    SALES_ENABLED: bool = Field(default=True)
    SUPPLIER_ORDERS_ENABLED: bool = Field(default=True)
    PAYMENTS_ENABLED: bool = Field(default=True)

    # Pricing
    DEFAULT_MIN_MARGIN_PERCENT: float = Field(default=5.0)
    DEFAULT_PAYMENT_FEE_PERCENT: float = Field(default=2.0)
    DEFAULT_PAYMENT_FIXED_FEE: float = Field(default=500.0)
    DEFAULT_SAFETY_BUFFER_PERCENT: float = Field(default=2.0)
    DEFAULT_PLATFORM_MARGIN_PERCENT: float = Field(default=10.0)

    DEFAULT_MARKETPLACE_COMMISSION: float = Field(default=10.0)
    DEFAULT_DONATION_FEE: float = Field(default=5.0)

    ENABLE_REGISTRATION: bool = Field(default=True)
    ENABLE_MARKETPLACE: bool = Field(default=True)
    ENABLE_DONATIONS: bool = Field(default=True)
    ENABLE_WALLET: bool = Field(default=True)

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        # fallback to sqlite for dev if mysql not configured
        if self.MYSQL_HOST and self.MYSQL_DATABASE and self.MYSQL_USER:
            return f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        return "sqlite+aiosqlite:///./vyron.db"

    @property
    def sync_database_url(self) -> str:
        url = self.effective_database_url
        # Convert async url to sync for alembic / sync operations
        if "mysql+asyncmy" in url:
            return url.replace("mysql+asyncmy", "mysql+aiomysql")
        if "sqlite+aiosqlite" in url:
            return url.replace("sqlite+aiosqlite", "sqlite")
        return url

    @property
    def admin_telegram_ids_list(self) -> List[int]:
        if not self.ADMIN_TELEGRAM_IDS:
            return []
        ids = []
        for part in self.ADMIN_TELEGRAM_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in ("development", "dev", "local")

    @field_validator("APP_SECRET")
    @classmethod
    def validate_secret(cls, v: str) -> str:
        if len(v) < 16:
            # allow short in dev but warn
            pass
        return v

settings = Settings()

def get_settings() -> Settings:
    return settings
