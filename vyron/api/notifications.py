"""User notifications API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import Notification, User
from vyron.errors import NotFoundError
from vyron.security.rbac import get_current_user
from vyron.services import notification_service
from vyron.web.serializers import notification_public

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    total = query.count()
    items = query.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    unread = db.query(Notification).filter(Notification.user_id == user.id, Notification.read_at.is_(None)).count()
    result = paginated([notification_public(n) for n in items], total, page, page_size)
    result["unread"] = unread
    return result


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if notification is None:
        raise NotFoundError("Notification not found.")
    notification_service.mark_notifications_read(db, user.id, notification.id)
    return ok(notification_public(notification))


@router.post("/read-all")
def mark_all_read(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    count = notification_service.mark_notifications_read(db, user.id)
    return ok({"marked": count})


@router.delete("/{notification_id}")
def delete_notification(notification_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    notification = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user.id).first()
    if notification is None:
        raise NotFoundError("Notification not found.")
    db.delete(notification)
    db.commit()
    return ok(message_code="NOTIFICATION_DELETED")
