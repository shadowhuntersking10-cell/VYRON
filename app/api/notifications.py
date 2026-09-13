"""Notifications API."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app import models
from app.dependencies import Db, require_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifs(request: Request, db: Db, page: int = 1, per_page: int = 20):
    user = require_user(request, db)
    q = db.query(models.Notification).filter_by(user_id=user.id).order_by(models.Notification.id.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    unread = db.query(models.Notification).filter_by(user_id=user.id, is_read=False).count()
    return {"items": [{"id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
                       "link": n.link, "read": n.is_read,
                       "created_at": n.created_at.isoformat()} for n in items],
            "total": total, "unread": unread}


@router.post("/{notif_id}/read")
def mark_read(notif_id: int, request: Request, db: Db):
    user = require_user(request, db)
    n = db.query(models.Notification).filter_by(id=notif_id, user_id=user.id).first()
    if n:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all(request: Request, db: Db):
    user = require_user(request, db)
    db.query(models.Notification).filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.commit()
    return {"ok": True}
