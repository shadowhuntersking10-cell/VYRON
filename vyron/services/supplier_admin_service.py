"""Supplier admin service — CRUD with encrypted credential storage.

Secrets (base_url/api_key/api_secret) are written to `encrypted_config`
(Fernet) and are NEVER returned by any serializer or logged.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.models import Supplier, User
from vyron.enums import SupplierStatus
from vyron.errors import ValidationError
from vyron.security.crypto import encrypt_json
from vyron.services import audit_service
from vyron.services.catalog_service import _unique_slug, slugify

PROVIDER_KINDS = {"http_json"}


def upsert_supplier(db: DbSession, admin: User, supplier: Optional[Supplier], payload: Dict[str, Any]) -> Supplier:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationError("Supplier name is required.", code="NAME_REQUIRED")
    provider_kind = str(payload.get("provider_kind", "http_json")).strip().lower()
    if provider_kind not in PROVIDER_KINDS:
        raise ValidationError(f"Unsupported provider kind '{provider_kind}'.", code="PROVIDER_KIND_INVALID")

    if supplier is None:
        supplier = Supplier(name=name[:140], slug=_unique_slug(db, Supplier, slugify(name)), provider_kind=provider_kind)
        db.add(supplier)
        action = "supplier.created"
    else:
        action = "supplier.updated"
        if payload.get("slug"):
            supplier.slug = _unique_slug(db, Supplier, slugify(str(payload["slug"])), exclude_id=supplier.id)

    supplier.name = name[:140]
    supplier.provider_kind = provider_kind
    supplier.priority = int(payload.get("priority", supplier.priority if supplier.priority is not None else 100))
    if payload.get("active") is not None:
        supplier.active = bool(payload["active"])
    status = str(payload.get("status", supplier.status or SupplierStatus.INACTIVE.value)).upper()
    if status not in {s.value for s in SupplierStatus}:
        raise ValidationError("Invalid supplier status.", code="STATUS_INVALID")
    supplier.status = status

    config = dict(supplier.config or {})
    for key in ("timeout_seconds", "max_retries", "products_endpoint", "order_endpoint", "status_endpoint", "balance_endpoint"):
        if key in payload:
            config[key] = payload[key]
    supplier.config = config

    secrets_changed = False
    secret_cfg: Dict[str, str] = {}
    for key in ("base_url", "api_key", "api_secret"):
        value = payload.get(key)
        if value:
            secret_cfg[key] = str(value).strip()
            secrets_changed = True
    if secrets_changed:
        # merge over existing encrypted secrets so partial updates don't wipe credentials
        existing: Dict[str, Any] = {}
        if supplier.encrypted_config:
            from vyron.security.crypto import decrypt_json

            try:
                existing = decrypt_json(supplier.encrypted_config) or {}
            except Exception:
                existing = {}
        existing.update(secret_cfg)
        supplier.encrypted_config = encrypt_json(existing)

    db.commit()
    audit_service.record_admin_action(db, admin, action, target_type="supplier", target_id=supplier.id, data={"name": supplier.name, "secrets_changed": secrets_changed})
    return supplier
