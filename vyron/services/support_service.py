"""Support tickets service."""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import Order, SupportMessage, SupportTicket, User
from vyron.enums import STAFF_ROLES, TicketPriority, TicketStatus, UserRole
from vyron.errors import ForbiddenError, ValidationError
from vyron.services import notification_service, settings_service


def _next_ticket_number(db: DbSession) -> str:
    count = db.query(SupportTicket).count() + 1
    return f"SUP-{count:06d}"


def create_ticket(
    db: DbSession,
    user: User,
    *,
    subject: str,
    message: str,
    order_id: Optional[str] = None,
    priority: str = TicketPriority.NORMAL.value,
) -> SupportTicket:
    subject = (subject or "").strip()
    message = (message or "").strip()
    if len(subject) < 3:
        raise ValidationError("Subject is too short.", code="SUBJECT_TOO_SHORT")
    if len(message) < 3:
        raise ValidationError("Message is too short.", code="MESSAGE_TOO_SHORT")
    max_open = settings_service.get_int_setting(db, "max_open_tickets_per_user", 5)
    open_count = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.user_id == user.id,
            SupportTicket.status.in_([TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value, TicketStatus.WAITING_USER.value]),
        )
        .count()
    )
    if open_count >= max_open:
        raise ValidationError(f"You have too many open tickets (max {max_open}).", code="TOO_MANY_TICKETS")

    if order_id:
        order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
        if order is None:
            raise ValidationError("Unknown order.", code="ORDER_NOT_FOUND")

    ticket = SupportTicket(
        number=_next_ticket_number(db),
        user_id=user.id,
        subject=subject[:200],
        order_id=order_id or None,
        status=TicketStatus.OPEN.value,
        priority=priority if priority in {p.value for p in TicketPriority} else TicketPriority.NORMAL.value,
    )
    db.add(ticket)
    db.flush()
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            author_id=user.id,
            author_role=user.role,
            author_name=user.name,
            body=message[:5000],
        )
    )
    db.commit()
    return ticket


def reply_ticket(db: DbSession, ticket: SupportTicket, author: User, body: str, is_internal: bool = False) -> SupportMessage:
    body = (body or "").strip()
    if not body:
        raise ValidationError("Message is empty.", code="MESSAGE_TOO_SHORT")
    is_staff = UserRole(author.role) in STAFF_ROLES
    if not is_staff and author.id != ticket.user_id:
        raise ForbiddenError()
    if is_internal and not is_staff:
        raise ForbiddenError()

    message = SupportMessage(
        ticket_id=ticket.id,
        author_id=author.id,
        author_role=author.role,
        author_name=author.name if is_staff else (author.name or author.username),
        body=body[:5000],
        is_internal=is_internal,
    )
    db.add(message)
    ticket.last_message_at = utcnow()

    if is_staff and not is_internal:
        ticket.status = TicketStatus.WAITING_USER.value
        user = db.get(User, ticket.user_id)
        if user:
            notification_service.notify_event(
                db, user, "support_response", {"number": ticket.number}, link=f"/support?ticket={ticket.id}", commit=False
            )
    elif not is_staff:
        if ticket.status in {TicketStatus.WAITING_USER.value, TicketStatus.RESOLVED.value}:
            ticket.status = TicketStatus.OPEN.value
    db.commit()
    return message


def set_ticket_status(db: DbSession, ticket: SupportTicket, staff: User, status: str) -> SupportTicket:
    if UserRole(staff.role) not in STAFF_ROLES:
        raise ForbiddenError()
    if status not in {s.value for s in TicketStatus}:
        raise ValidationError("Invalid status.", code="STATUS_INVALID")
    ticket.status = status
    db.commit()
    return ticket


def list_tickets(
    db: DbSession, *, user: Optional[User] = None, staff: bool = False, status: Optional[str] = None, page: int = 1, page_size: int = 20
) -> Dict[str, object]:
    query = db.query(SupportTicket)
    if not staff:
        if user is None:
            return {"items": [], "total": 0}
        query = query.filter(SupportTicket.user_id == user.id)
    if status:
        query = query.filter(SupportTicket.status == status)
    total = query.count()
    items = query.order_by(SupportTicket.last_message_at.desc()).offset((max(1, page) - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def visible_messages(db: DbSession, ticket: SupportTicket, viewer: User) -> List[SupportMessage]:
    is_staff = UserRole(viewer.role) in STAFF_ROLES
    messages = ticket.messages
    if not is_staff:
        messages = [m for m in messages if not m.is_internal]
    return messages
