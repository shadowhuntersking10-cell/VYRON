from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(q: str = "", db: AsyncSession = Depends(get_db)):
    return await search_service.global_search(db, q)
