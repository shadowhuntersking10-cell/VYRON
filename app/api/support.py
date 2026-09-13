from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import SupportTicket, SupportMessage, User
from app.utils.security import generate_idempotency_key
import secrets

router = APIRouter(prefix="/api/support", tags=["support"])

@router.get("/tickets")
async def list_tickets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(SupportTicket).where(SupportTicket.user_id == current_user.id).order_by(SupportTicket.created_at.desc()))
    tickets = result.scalars().all()
    return [{"id": t.id, "ticket_number": t.ticket_number, "subject": t.subject, "status": t.status, "category": t.category, "created_at": t.created_at.isoformat()} for t in tickets]

@router.post("/tickets")
async def create_ticket(payload: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    subject = payload.get("subject")
    message = payload.get("message")
    category = payload.get("category", "GENERAL")
    if not subject or not message:
        raise HTTPException(status_code=400, detail="Subject and message required")

    ticket_number = f"TKT-{secrets.token_hex(4).upper()}"
    ticket = SupportTicket(
        ticket_number=ticket_number,
        user_id=current_user.id,
        subject=subject,
        category=category,
        status="OPEN"
    )
    db.add(ticket)
    await db.flush()

    msg = SupportMessage(
        ticket_id=ticket.id,
        user_id=current_user.id,
        message=message
    )
    db.add(msg)
    await db.commit()

    return {"success": True, "ticket": {"id": ticket.id, "ticket_number": ticket.ticket_number}}

@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id, SupportTicket.user_id == current_user.id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    result = await db.execute(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id).order_by(SupportMessage.created_at.asc()))
    messages = result.scalars().all()

    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "subject": ticket.subject,
        "status": ticket.status,
        "category": ticket.category,
        "messages": [{"id": m.id, "message": m.message, "user_id": m.user_id, "created_at": m.created_at.isoformat()} for m in messages]
    }

@router.post("/tickets/{ticket_id}/messages")
async def add_message(ticket_id: int, payload: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id, SupportTicket.user_id == current_user.id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    message = payload.get("message")
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    msg = SupportMessage(ticket_id=ticket.id, user_id=current_user.id, message=message)
    db.add(msg)
    from datetime import datetime
    ticket.last_message_at = datetime.utcnow()
    ticket.status = "OPEN"
    await db.commit()

    return {"success": True, "message_id": msg.id}
