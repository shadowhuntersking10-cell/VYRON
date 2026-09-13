from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Favorite, User

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavIn(BaseModel):
    kind: str
    ref_id: int


@router.get("")
async def list_favs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Favorite).where(Favorite.user_id == user.id))).scalars().all()
    return [{"kind": f.kind, "ref_id": f.ref_id} for f in rows]


@router.post("/toggle")
async def toggle(data: FavIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if data.kind not in ("game", "product", "listing"):
        raise HTTPException(400, "bad_kind")
    existing = (await db.execute(select(Favorite).where(
        Favorite.user_id == user.id, Favorite.kind == data.kind, Favorite.ref_id == data.ref_id))).scalars().first()
    if existing:
        await db.delete(existing)
        await db.commit()
        return {"favorited": False}
    db.add(Favorite(user_id=user.id, kind=data.kind, ref_id=data.ref_id))
    await db.commit()
    return {"favorited": True}
