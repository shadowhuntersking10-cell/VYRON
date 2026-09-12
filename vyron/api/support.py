"""Support tickets API (user side)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import SupportTicket, User
from vyron.enums import STAFF_ROLES, UserRole
from vyron.errors import ForbiddenError, NotFoundError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user
from vyron.services import support_service
from vyron.web.serializers import ticket_public

router = APIRouter(prefix="/api/support", tags=["support"])


@router.get("/tickets")
def my_tickets(
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    data = support_service.list_tickets(db, user=user, page=page, page_size=page_size)
    return paginated(
        [{"id": t.id, "number": t.number, "subject": t.subject, "status": t.status, "priority": t.priority,
          "created_at": t.created_at.isoformat() if t.created_at else None,
          "last_message_at": t.last_message_at.isoformat() if t.last_message_at else None} for t in data["items"]],
        data["total"], page, page_size,
    )


@router.post("/tickets")
def create_ticket(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "ticket", "5/hour", user_id=user.id)
    ticket = support_service.create_ticket(
        db, user,
        subject=str(payload.get("subject", "")),
        message=str(payload.get("message", "")),
        order_id=payload.get("order_id"),
        priority=str(payload.get("priority", "NORMAL")),
    )
    return ok({"id": ticket.id, "number": ticket.number}, message_code="TICKET_CREATED")


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise NotFoundError("Ticket not found.")
    if ticket.user_id != user.id and UserRole(user.role) not in STAFF_ROLES:
        raise ForbiddenError()
    return ok(ticket_public(ticket, user.role))


@router.post("/tickets/{ticket_id}/messages")
def reply(
    ticket_id: str,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if ticket is None:
        raise NotFoundError("Ticket not found.")
    if ticket.user_id != user.id:
        raise ForbiddenError()
    message = support_service.reply_ticket(db, ticket, user, str(payload.get("body", "")))
    return ok({"id": message.id, "created_at": message.created_at.isoformat() if message.created_at else None}, message_code="MESSAGE_SENT")
