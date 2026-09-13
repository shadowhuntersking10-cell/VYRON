"""Support tickets."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SupportMessage, SupportTicket
from app.services.notification_service import notify_user

STATUSES = ("OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED")


async def create_ticket(db: AsyncSession, *, user_id: int | None, subject: str, category: str, body: str, order_id: int | None = None, attachments: list | None = None) -> SupportTicket:
    ticket = SupportTicket(user_id=user_id, subject=subject.strip(), category=category or "general",
                           status="OPEN", order_id=order_id)
    db.add(ticket)
    await db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, sender_id=user_id, is_admin=False, body=body.strip(),
                          attachments=(attachments or [])[:5]))
    await db.flush()
    return ticket


async def reply(db: AsyncSession, ticket: SupportTicket, *, sender_id: int | None, body: str, is_admin: bool, attachments: list | None = None) -> SupportMessage:
    msg = SupportMessage(ticket_id=ticket.id, sender_id=sender_id, is_admin=is_admin, body=body.strip(),
                         attachments=(attachments or [])[:5])
    db.add(msg)
    ticket.status = "WAITING_USER" if is_admin else "IN_PROGRESS"
    await db.flush()
    target = ticket.user_id if is_admin else None
    if target and target != sender_id:
        await notify_user(db, user_id=target, kind="support", title="Support reply",
                          body=f"Ticket #{ticket.id}: {ticket.subject}", link=f"/support/{ticket.id}")
    return msg


async def set_status(db: AsyncSession, ticket: SupportTicket, status: str) -> SupportTicket:
    if status not in STATUSES:
        raise ValueError("bad_status")
    ticket.status = status
    await db.flush()
    return ticket


async def messages(db: AsyncSession, ticket_id: int) -> list[SupportMessage]:
    stmt = select(SupportMessage).where(SupportMessage.ticket_id == ticket_id).order_by(SupportMessage.id)
    return list((await db.execute(stmt)).scalars().all())
