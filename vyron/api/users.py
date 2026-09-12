"""Current-user profile API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.db.models import User
from vyron.errors import ValidationError
from vyron.i18n import SUPPORTED_LANGUAGES
from vyron.security.rbac import get_current_user
from vyron.services import audit_service
from vyron.web.serializers import user_public

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me")
def me(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(user_public(user))


@router.put("/me")
def update_me(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if "name" in payload:
        name = str(payload["name"]).strip()
        if len(name) < 2:
            raise ValidationError("Name is too short.", code="NAME_TOO_SHORT")
        user.name = name[:120]
    if "phone" in payload:
        user.phone = (str(payload["phone"] or "").strip()[:32]) or None
    if "locale" in payload and payload["locale"] in SUPPORTED_LANGUAGES:
        user.locale = payload["locale"]
    if "theme" in payload and payload["theme"] in {"light", "dark", "system"}:
        user.theme = payload["theme"]
    if "avatar_url" in payload:
        user.avatar_url = (str(payload["avatar_url"] or "").strip()[:500]) or None
    db.commit()
    audit_service.record_audit(db, "user.profile_updated", actor_id=user.id, actor_type="USER", entity_type="user", entity_id=user.id)
    return ok(user_public(user), message_code="PROFILE_SAVED")
