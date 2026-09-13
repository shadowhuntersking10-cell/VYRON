from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services import media_service

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("/upload")
async def upload(kind: str = "listing", file: UploadFile = File(...),
                user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        rec = await media_service.save_upload(db, file, kind=kind, owner_id=user.id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"url": rec.url, "mime": rec.mime, "size": rec.size_bytes}
