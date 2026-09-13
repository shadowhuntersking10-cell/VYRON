"""DB-backed settings (override env defaults) + audit logging."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app import models


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(models.Setting).filter_by(key=key).first()
    return row.value if row else default


def set_setting(db: Session, key: str, value: str, description: str = "") -> models.Setting:
    row = db.query(models.Setting).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        row = models.Setting(key=key, value=value, description=description)
        db.add(row)
    db.flush()
    return row


def audit(db: Session, admin_id: int | None, action: str, entity: str = "",
          entity_id: str = "", old=None, new=None, ip: str = "") -> None:
    def dump(v):
        if v is None:
            return ""
        try:
            return json.dumps(v, default=str)[:4000]
        except Exception:
            return str(v)[:4000]

    db.add(models.AuditLog(
        admin_id=admin_id, action=action, entity=entity, entity_id=str(entity_id),
        old_value=dump(old), new_value=dump(new), ip=ip or "",
    ))
    db.flush()
