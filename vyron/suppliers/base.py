"""Supplier provider abstraction.

Every supplier is an adapter implementing SupplierProvider. The core order
system never hardcodes a supplier; the SupplierRouter selects adapters based on
mapping, priority, availability and price, records every attempt and follows
strict rules on UNKNOWN outcomes (reconcile first, never blindly re-submit).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class SupplierProductInfo:
    external_id: str
    name: str
    cost: Decimal
    currency: str = "USD"
    available: bool = True
    stock: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecipientValidation:
    valid: bool
    reason: str = ""
    normalized: Dict[str, Any] = field(default_factory=dict)
    display_name: Optional[str] = None  # e.g. resolved player nickname


@dataclass
class SupplierOrderResult:
    status: str                      # SUCCESS | PROCESSING | FAILED | UNKNOWN
    external_order_id: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = False          # safe to try another supplier / retry
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupplierStatusResult:
    status: str                      # SUCCESS | PROCESSING | FAILED | UNKNOWN | CANCELLED | REFUNDED
    error: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BalanceResult:
    balance: Optional[Decimal]
    currency: str = "USD"
    raw: Dict[str, Any] = field(default_factory=dict)


class SupplierProviderError(Exception):
    """Transport-level failure where the order outcome is UNKNOWN.

    Timeouts / connection errors MUST surface as UNKNOWN — the router then
    reconciles before any new attempt (never duplicates a paid delivery).
    """

    def __init__(self, message: str, retryable: bool = True) -> None:
        self.retryable = retryable
        super().__init__(message)


class SupplierProvider(ABC):
    """Interface every supplier adapter implements."""

    kind: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """True only when the supplier has all required credentials/config."""

    @abstractmethod
    def get_products(self) -> List[SupplierProductInfo]:
        """Fetch the supplier's catalog (for mapping/sync)."""

    @abstractmethod
    def get_product(self, external_product_id: str) -> Optional[SupplierProductInfo]:
        """Fetch one product (availability/price check)."""

    @abstractmethod
    def get_balance(self) -> BalanceResult:
        """Current supplier balance (admin visibility)."""

    @abstractmethod
    def validate_recipient(self, external_product_id: str, fields: Dict[str, Any]) -> RecipientValidation:
        """Validate the recipient (e.g. playerId) BEFORE creating an order."""

    @abstractmethod
    def create_order(
        self,
        external_product_id: str,
        fields: Dict[str, Any],
        quantity: int,
        idempotency_key: str,
    ) -> SupplierOrderResult:
        """Create the supplier order. MUST pass the idempotency key through to
        the supplier when supported, and MUST raise SupplierProviderError (=>
        UNKNOWN) on timeouts instead of guessing."""

    @abstractmethod
    def get_order_status(self, external_order_id: str) -> SupplierStatusResult:
        """Poll/reconcile an order previously submitted."""

    @abstractmethod
    def cancel_order(self, external_order_id: str) -> SupplierStatusResult:
        """Cancel an order that has not been delivered."""

    @abstractmethod
    def refund_order(self, external_order_id: str, reason: str) -> SupplierStatusResult:
        """Request refund for a failed/partially failed supplier order."""

    def test_connection(self) -> Dict[str, Any]:
        """Admin 'Test connection' action. Default: balance check."""
        balance = self.get_balance()
        return {"ok": balance.balance is not None, "balance": str(balance.balance) if balance.balance is not None else None}
