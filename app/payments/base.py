"""Payment provider abstraction."""
from __future__ import annotations


class ProviderStatus:
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class PaymentProvider:
    name = "base"

    def is_configured(self) -> bool:
        return False

    def status(self) -> str:
        return ProviderStatus.CONFIGURED if self.is_configured() else ProviderStatus.NOT_CONFIGURED

    def create_payment(self, payment, order, return_url: str = "") -> dict:
        """Return {'action': 'redirect'|'qr'|'instructions', ...}. Must not mark paid."""
        raise NotImplementedError

    def verify_webhook(self, data: dict, headers: dict) -> tuple[bool, str]:
        """Verify signature. Returns (valid, external_id)."""
        raise NotImplementedError

    def parse_webhook(self, data: dict) -> dict:
        """Normalize to {'external_id','amount','status','paid':bool}."""
        raise NotImplementedError


PROVIDERS: dict[str, PaymentProvider] = {}


def register(cls):
    PROVIDERS[cls.name] = cls()
    return cls
