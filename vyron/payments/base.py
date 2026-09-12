"""Payment provider abstraction.

One interface, pluggable adapters (Payme, Click, Stripe, ...).

Hard rules:
- the frontend NEVER decides payment success; only server-verified provider
  events (webhooks / status checks) may move money state
- missing credentials => ProviderNotConfiguredError (never faked success)
- every webhook is signature-verified before parsing
- amounts are Decimal end to end
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass
class PaymentRequest:
    payment_id: str                    # VYRON payment UUID (merchant reference)
    amount: Decimal                    # exact money
    currency: str
    description: str
    return_url: str
    cancel_url: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    locale: str = "en"


@dataclass
class PaymentResult:
    provider: str
    status: str                        # PENDING | PAID | FAILED | CANCELLED | EXPIRED
    provider_payment_id: Optional[str] = None
    checkout_url: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RefundResult:
    provider: str
    status: str                        # COMPLETED | PROCESSING | FAILED
    provider_refund_id: Optional[str] = None
    amount: Optional[Decimal] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookRequest:
    headers: Dict[str, str]            # lowercased header names
    body: bytes                        # RAW body (signature verification)
    query: Dict[str, str] = field(default_factory=dict)


@dataclass
class WebhookEvent:
    provider: str
    event_id: str                      # provider-side unique id (dedupe key)
    event_type: str                    # PAYMENT_PAID | PAYMENT_FAILED | PAYMENT_REFUNDED | ...
    status: str                        # PAID | FAILED | REFUNDED | CANCELLED
    merchant_reference: Optional[str] = None   # our payment_id echoed back
    provider_payment_id: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class PaymentProvider(ABC):
    """Interface every VYRON payment adapter implements."""

    name: str = "base"
    display_name: str = "Base provider"

    @abstractmethod
    def is_configured(self) -> bool:
        """True only when ALL required credentials are present."""

    @abstractmethod
    def create_payment(self, request: PaymentRequest) -> PaymentResult:
        """Create a payment/checkout session with the provider."""

    @abstractmethod
    def verify_payment(self, provider_payment_id: str) -> PaymentResult:
        """Server-side status check (reconciliation, return-page verification)."""

    @abstractmethod
    def parse_webhook(self, request: WebhookRequest) -> WebhookEvent:
        """Verify signature/authenticity of the raw request and parse the event.

        MUST raise WebhookVerificationError when the request is not authentic.
        """

    @abstractmethod
    def refund_payment(
        self, provider_payment_id: str, amount: Decimal, reason: str, idempotency_key: Optional[str] = None
    ) -> RefundResult:
        """Issue a (partial) refund through the provider."""

    def build_return_url_with_reference(self, base_url: str, provider_payment_id: str) -> str:
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}payment_ref={provider_payment_id}"
