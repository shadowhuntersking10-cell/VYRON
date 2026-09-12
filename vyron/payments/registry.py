"""Payment provider registry — one place that knows all adapters."""

from __future__ import annotations

from typing import Dict, List

from vyron.config import settings
from vyron.errors import ProviderNotConfiguredError
from vyron.payments.base import PaymentProvider
from vyron.payments.providers.click import ClickProvider
from vyron.payments.providers.payme import PaymeProvider
from vyron.payments.providers.stripe import StripeProvider

_REGISTRY: Dict[str, PaymentProvider] = {}


def _build_registry() -> Dict[str, PaymentProvider]:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = {
            "payme": PaymeProvider(),
            "click": ClickProvider(),
            "stripe": StripeProvider(),
        }
    return _REGISTRY


def get_provider(name: str | None = None) -> PaymentProvider:
    registry = _build_registry()
    provider_name = (name or settings.payment_provider or "").strip().lower()
    if not provider_name:
        raise ProviderNotConfiguredError(
            "No default payment provider configured (PAYMENT_PROVIDER is empty).",
            code="PAYMENT_PROVIDER_NOT_CONFIGURED",
        )
    provider = registry.get(provider_name)
    if provider is None:
        raise ProviderNotConfiguredError(f"Unknown payment provider '{provider_name}'.", code="PAYMENT_PROVIDER_UNKNOWN")
    return provider


def get_configured_providers() -> List[PaymentProvider]:
    return [p for p in _build_registry().values() if p.is_configured()]


def provider_status() -> List[dict]:
    """For admin panel & checkout: which providers exist and are configured."""
    return [
        {"name": p.name, "display_name": p.display_name, "configured": p.is_configured()}
        for p in _build_registry().values()
    ]
