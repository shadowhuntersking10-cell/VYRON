from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import SupportTicket, User
from app.schemas import TicketIn
from app.services import support_service

router = APIRouter(prefix="/api/support", tags=["support"])


class ReplyIn(BaseModel):
    body: str
    attachments: list[str] = []


@router.get("/tickets")
async def my_tickets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.id.desc()))).scalars().all()
    return [{"id": t.id, "subject": t.subject, "category": t.category, "status": t.status,
             "created_at": t.created_at.isoformat()} for t in rows]


@router.post("/tickets")
async def create_ticket(data: TicketIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ticket = await support_service.create_ticket(db, user_id=user.id, subject=data.subject,
                                                 category=data.category, body=data.body, order_id=data.order_id,
                                                 attachments=data.attachments)
    await db.commit()
    return {"id": ticket.id, "status": ticket.status}


@router.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket or (ticket.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(404, "ticket_not_found")
    msgs = await support_service.messages(db, ticket.id)
    return {"id": ticket.id, "subject": ticket.subject, "status": ticket.status,
            "messages": [{"is_admin": m.is_admin, "body": m.body, "attachments": m.attachments or [],
                          "created_at": m.created_at.isoformat()} for m in msgs]}


@router.post("/tickets/{ticket_id}/reply")
async def reply(ticket_id: int, data: ReplyIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket or (ticket.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(404, "ticket_not_found")
    is_admin = user.role == "ADMIN"
    await support_service.reply(db, ticket, sender_id=user.id, body=data.body, is_admin=is_admin, attachments=data.attachments)
    await db.commit()
    return {"ok": True}
