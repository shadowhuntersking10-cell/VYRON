from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import Favorite, User

router = APIRouter(prefix="/api/favorites", tags=["favorites"])

@router.get("/")
async def list_favorites(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Favorite).where(Favorite.user_id == current_user.id).order_by(Favorite.created_at.desc()))
    favs = result.scalars().all()
    return [{"id": f.id, "entity_type": f.entity_type, "entity_id": f.entity_id, "created_at": f.created_at.isoformat()} for f in favs]

@router.post("/")
async def add_favorite(payload: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    entity_type = payload.get("entity_type")
    entity_id = payload.get("entity_id")
    if not entity_type or not entity_id:
        raise HTTPException(status_code=400, detail="entity_type and entity_id required")
    if entity_type not in ("game", "product", "listing"):
        raise HTTPException(status_code=400, detail="Invalid entity_type")

    result = await db.execute(select(Favorite).where(Favorite.user_id == current_user.id, Favorite.entity_type == entity_type, Favorite.entity_id == entity_id))
    if result.scalar_one_or_none():
        return {"success": True, "message": "Already favorited"}

    fav = Favorite(user_id=current_user.id, entity_type=entity_type, entity_id=entity_id)
    db.add(fav)
    await db.commit()
    return {"success": True, "id": fav.id}

@router.delete("/{fav_id}")
async def remove_favorite(fav_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Favorite).where(Favorite.id == fav_id, Favorite.user_id == current_user.id))
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")
    await db.delete(fav)
    await db.commit()
    return {"success": True}
