"""Support tickets API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app import models
from app.dependencies import Db, require_user
from app.schemas import MessageIn, TicketIn

router = APIRouter(prefix="/api/support", tags=["support"])


@router.get("/tickets")
def my_tickets(request: Request, db: Db):
    user = require_user(request, db)
    tickets = db.query(models.SupportTicket).filter_by(user_id=user.id).order_by(
        models.SupportTicket.id.desc()).all()
    return {"items": [{"id": t.id, "subject": t.subject, "category": t.category,
                       "status": t.status, "created_at": t.created_at.isoformat()} for t in tickets]}


@router.post("/tickets")
def create_ticket(body: TicketIn, request: Request, db: Db):
    user = require_user(request, db)
    t = models.SupportTicket(user_id=user.id, subject=body.subject, category=body.category, status="OPEN")
    db.add(t)
    db.flush()
    db.add(models.SupportMessage(ticket_id=t.id, author_id=user.id, is_staff=False, body=body.body[:5000]))
    db.commit()
    return {"ok": True, "id": t.id}


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: int, request: Request, db: Db):
    user = require_user(request, db)
    t = db.get(models.SupportTicket, ticket_id)
    if not t or (t.user_id != user.id):
        # allow admin via separate check
        from app.dependencies import user_roles
        if "admin" not in user_roles(user):
            raise HTTPException(status_code=404, detail="ticket_not_found")
    msgs = db.query(models.SupportMessage).filter_by(ticket_id=t.id).order_by(models.SupportMessage.id).all()
    return {"id": t.id, "subject": t.subject, "status": t.status,
            "messages": [{"author": m.author_id, "staff": m.is_staff, "body": m.body,
                          "created_at": m.created_at.isoformat()} for m in msgs]}


@router.post("/tickets/{ticket_id}/messages")
def reply(ticket_id: int, body: MessageIn, request: Request, db: Db):
    user = require_user(request, db)
    from app.dependencies import user_roles
    t = db.get(models.SupportTicket, ticket_id)
    if not t:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    is_admin = "admin" in user_roles(user)
    if t.user_id != user.id and not is_admin:
        raise HTTPException(status_code=404, detail="ticket_not_found")
    db.add(models.SupportMessage(ticket_id=t.id, author_id=user.id, is_staff=is_admin, body=body.body[:5000]))
    if is_admin:
        t.status = "WAITING_USER"
    elif t.status in ("WAITING_USER", "RESOLVED"):
        t.status = "OPEN"
    db.commit()
    return {"ok": True}
