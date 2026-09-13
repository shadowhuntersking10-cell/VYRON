from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notes(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Notification).where(Notification.user_id == user.id)
                             .order_by(Notification.id.desc()).limit(50))).scalars().all()
    unread = (await db.execute(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.is_read.is_(False)))).scalar() or 0
    return {"unread": unread, "items": [
        {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
         "is_read": n.is_read, "created_at": n.created_at.isoformat()} for n in rows]}


@router.post("/{note_id}/read")
async def mark_read(note_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    note = await db.get(Notification, note_id)
    if note and note.user_id == user.id:
        note.is_read = True
        await db.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False)))).scalars().all()
    for n in rows:
        n.is_read = True
    await db.commit()
    return {"ok": True, "count": len(rows)}
