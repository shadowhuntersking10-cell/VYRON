"""Central application configuration.

All settings come from environment variables / .env (12-factor).
No secrets are ever hardcoded. Missing optional integrations degrade to
`configured == False` and raise structured *_NOT_CONFIGURED errors at use time.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Core -----------------------------------------------------------------
    vyron_env: str = "development"
    vyron_host: str = "0.0.0.0"
    vyron_port: int = 8000
    public_base_url: str = "http://localhost:8000"
    session_secret: str = ""
    allowed_origins: str = ""

    # --- Database (MySQL, required) --------------------------------------------
    database_url: str = "mysql+pymysql://vyron:vyron_dev_password@127.0.0.1:3306/vyron?charset=utf8mb4"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800
    db_echo: bool = False

    # --- Redis (required) ---------------------------------------------------------
    redis_url: str = "redis://127.0.0.1:6379/0"

    auto_migrate_on_start: bool = True

    # --- SMTP -----------------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = True
    smtp_from: str = "no-reply@vyron.app"

    # --- Telegram --------------------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_miniapp_url: str = ""
    admin_telegram_ids: str = ""

    # --- Payments ------------------------------------------------------------------------
    payment_provider: str = ""
    payme_merchant_id: str = ""
    payme_secret: str = ""
    click_merchant_id: str = ""
    click_service_id: str = ""
    click_secret: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""
    payment_success_redirect: str = ""
    payment_cancel_redirect: str = ""

    # --- Suppliers -------------------------------------------------------------------------
    supplier_api_key: str = ""
    supplier_api_secret: str = ""
    supplier_api_base_url: str = ""
    supplier_timeout_seconds: int = 30
    supplier_max_attempts: int = 3

    # --- S3 ---------------------------------------------------------------------------------
    s3_endpoint: str = ""
    s3_bucket: str = "vyron"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_secure: bool = True
    s3_public_url: str = ""
    upload_max_bytes: int = 5 * 1024 * 1024
    local_upload_dir: str = "static/uploads"

    # --- Revenue defaults (runtime-configurable via PlatformSetting) -----------------------------
    marketplace_commission_pct: float = 10.0
    donation_fee_pct: float = 5.0
    donation_fee_fixed: float = 0.0
    service_fee_pct: float = 0.0
    seller_holding_period_hours: int = 72
    min_payout_amount: float = 10.0
    promoted_listing_price: float = 5.0
    featured_listing_price: float = 10.0

    # --- Bootstrap -------------------------------------------------------------------------------
    admin_email: str = ""
    admin_password: str = ""
    admin_username: str = "vyron_admin"
    seed_demo_data: bool = True

    # --- Security -----------------------------------------------------------------------------------
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/hour"
    rate_limit_reset: str = "5/hour"
    rate_limit_webhook: str = "600/minute"
    csrf_enabled: bool = True
    trust_proxy_headers: bool = False
    session_ttl_days: int = 30
    bcrypt_fallback: bool = False

    # --- Observability ----------------------------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # --- Derived helpers -----------------------------------------------------------------------------
    @field_validator("vyron_env")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        v = v.lower()
        if v not in {"development", "staging", "production", "test"}:
            raise ValueError("VYRON_ENV must be development|staging|production|test")
        return v

    @property
    def is_production(self) -> bool:
        return self.vyron_env == "production"

    @property
    def is_test(self) -> bool:
        return self.vyron_env == "test"

    @property
    def cors_origins(self) -> List[str]:
        origins = {self.public_base_url.rstrip("/")}
        origins.update(_split_csv(self.allowed_origins))
        return sorted(origins)

    @property
    def admin_telegram_id_list(self) -> List[int]:
        ids: List[int] = []
        for raw in _split_csv(self.admin_telegram_ids):
            try:
                ids.append(int(raw))
            except ValueError:
                continue
        return ids

    @property
    def miniapp_url(self) -> str:
        if self.telegram_miniapp_url:
            return self.telegram_miniapp_url
        return f"{self.public_base_url.rstrip('/')}/miniapp"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)

    def payment_provider_configured(self, provider: str) -> bool:
        provider = provider.lower()
        if provider == "payme":
            return bool(self.payme_merchant_id and self.payme_secret)
        if provider == "click":
            return bool(self.click_merchant_id and self.click_secret)
        if provider == "stripe":
            return bool(self.stripe_secret_key)
        return False

    @property
    def supplier_configured(self) -> bool:
        return bool(self.supplier_api_base_url and self.supplier_api_key)

    def validate_core(self) -> List[str]:
        """Return a list of fatal configuration problems (empty == healthy)."""
        problems: List[str] = []
        if not self.session_secret or len(self.session_secret) < 32:
            problems.append(
                "SESSION_SECRET is missing or too short (need >= 32 chars; generate with: openssl rand -hex 32)"
            )
        if "sqlite" in self.database_url.lower():
            problems.append("DATABASE_URL must point at MySQL — SQLite is not supported by VYRON.")
        if not self.database_url.lower().startswith(("mysql", "mariadb")):
            problems.append("DATABASE_URL must use the MySQL dialect, e.g. mysql+pymysql://user:pass@host:3306/vyron")
        if self.is_production:
            if not self.public_base_url.startswith("https://"):
                problems.append("PUBLIC_BASE_URL must be https:// in production.")
            if self.seed_demo_data:
                problems.append("SEED_DEMO_DATA must be disabled in production.")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
