from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import GameOut
from app.services import catalog_service

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("", response_model=list[GameOut])
async def list_games(db: AsyncSession = Depends(get_db)):
    return await catalog_service.list_games(db)


@router.get("/{slug}", response_model=GameOut)
async def game_detail(slug: str, db: AsyncSession = Depends(get_db)):
    game = await catalog_service.get_game_by_slug(db, slug)
    if not game or not game.is_active:
        raise HTTPException(404, "game_not_found")
    return game
