"""Audit logging — system-wide trail for consequential actions."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.models import AdminAction, AuditLog, User


def record_audit(
    db: DbSession,
    action: str,
    *,
    actor_id: Optional[str] = None,
    actor_type: str = "SYSTEM",
    actor_role: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=_safe_json(before),
        after=_safe_json(after),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:400] or None,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def record_admin_action(
    db: DbSession,
    admin: User,
    action: str,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    reason: Optional[str] = None,
    data: Optional[dict] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> AdminAction:
    entry = AdminAction(
        admin_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=(reason or "")[:400] or None,
        data=_safe_json(data),
        ip_address=ip_address,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def _safe_json(value: Optional[dict]) -> Optional[dict]:
    if value is None:
        return None
    sanitized: dict[str, Any] = {}
    sensitive = {"password", "password_hash", "secret", "token", "api_key", "signature", "details_enc", "encrypted_config"}
    for key, item in value.items():
        if key.lower() in sensitive:
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = item
    return sanitized
