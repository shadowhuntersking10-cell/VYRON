from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.get("/")
async def list_notifications(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50))
    notifs = result.scalars().all()
    return [{"id": n.id, "type": n.type, "title": n.title, "message": n.message, "is_read": n.is_read, "created_at": n.created_at.isoformat(), "data": n.data} for n in notifs]

@router.post("/{notif_id}/read")
async def mark_read(notif_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Notification).where(Notification.id == notif_id, Notification.user_id == current_user.id))
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        from datetime import datetime
        notif.read_at = datetime.utcnow()
        await db.commit()
    return {"success": True}

@router.post("/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Notification).where(Notification.user_id == current_user.id, Notification.is_read == False))
    notifs = result.scalars().all()
    from datetime import datetime
    for n in notifs:
        n.is_read = True
        n.read_at = datetime.utcnow()
    await db.commit()
    return {"success": True, "marked": len(notifs)}
