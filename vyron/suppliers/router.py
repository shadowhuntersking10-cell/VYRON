"""SupplierRouter — builds adapters from Supplier rows and selects candidates.

Selection rules (per product variant):
1. mapped suppliers only (SupplierProduct rows)
2. supplier active + status ACTIVE
3. variant mapping available (+ stock if tracked)
4. ordered by supplier priority (asc), then cost (asc)
The delivery service walks the candidate list: safe failure -> next supplier;
UNKNOWN outcome -> STOP and reconcile first (never duplicate a paid delivery).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.models import Supplier, SupplierProduct
from vyron.enums import SupplierStatus
from vyron.logging import get_logger
from vyron.security.crypto import decrypt_json
from vyron.suppliers.base import SupplierProvider
from vyron.suppliers.providers.http_json import HttpJsonSupplierProvider

log = get_logger("vyron.suppliers.router")


@dataclass
class SupplierCandidate:
    supplier: Supplier
    mapping: SupplierProduct
    provider: SupplierProvider


def build_provider(supplier: Supplier) -> SupplierProvider:
    """Instantiate the adapter for a Supplier row (decrypting credentials)."""
    secret_cfg = {}
    if supplier.encrypted_config:
        try:
            secret_cfg = decrypt_json(supplier.encrypted_config) or {}
        except Exception as exc:
            log.error(f"cannot decrypt supplier config for {supplier.slug}: {exc}")
            secret_cfg = {}

    base_url = secret_cfg.get("base_url") or settings.supplier_api_base_url
    api_key = secret_cfg.get("api_key") or settings.supplier_api_key
    api_secret = secret_cfg.get("api_secret") or settings.supplier_api_secret
    config = dict(supplier.config or {})
    timeout = config.get("timeout_seconds") or settings.supplier_timeout_seconds

    if supplier.provider_kind == "http_json":
        return HttpJsonSupplierProvider(
            base_url=base_url or "", api_key=api_key or "", api_secret=api_secret or "", config=config, timeout_seconds=int(timeout)
        )
    log.warning(f"unknown supplier provider_kind '{supplier.provider_kind}' — falling back to http_json")
    return HttpJsonSupplierProvider(base_url=base_url or "", api_key=api_key or "", config=config, timeout_seconds=int(timeout))


def candidates_for_variant(db: DbSession, variant_id: str) -> List[SupplierCandidate]:
    rows: List[Tuple[SupplierProduct, Supplier]] = (
        db.query(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .filter(SupplierProduct.variant_id == variant_id)
        .filter(SupplierProduct.available.is_(True))
        .filter(Supplier.active.is_(True), Supplier.status == SupplierStatus.ACTIVE.value)
        .order_by(Supplier.priority.asc(), SupplierProduct.supplier_cost.asc())
        .all()
    )
    candidates: List[SupplierCandidate] = []
    for mapping, supplier in rows:
        if mapping.stock is not None and mapping.stock <= 0:
            continue
        try:
            provider = build_provider(supplier)
        except Exception as exc:
            log.error(f"failed to build provider for supplier {supplier.slug}: {exc}")
            continue
        if not provider.is_configured():
            log.warning(f"supplier '{supplier.slug}' is not configured (no base_url) — skipping")
            continue
        candidates.append(SupplierCandidate(supplier=supplier, mapping=mapping, provider=provider))
    return candidates


def get_provider_for_supplier(db: DbSession, supplier_id: str) -> Optional[SupplierProvider]:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        return None
    return build_provider(supplier)
