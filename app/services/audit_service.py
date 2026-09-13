"""Audit logging for admin + financial actions."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    action: str,
    actor_id: int | None = None,
    entity: str | None = None,
    entity_id: str | int | None = None,
    ip: str | None = None,
    meta: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        ip=(ip or "")[:64] or None,
        meta=meta,
    )
    db.add(entry)
    await db.flush()
    return entry
