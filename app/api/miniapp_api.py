"""Aggregated endpoints optimised for the Telegram Mini App."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Game, Order, Product, Promotion
from app.schemas import GameOut, ProductOut

router = APIRouter(prefix="/api/miniapp", tags=["miniapp"])


@router.get("/home")
async def miniapp_home(db: AsyncSession = Depends(get_db)):
    games = (await db.execute(select(Game).where(Game.is_active.is_(True))
                              .order_by(Game.is_featured.desc(), Game.sort_order).limit(12))).scalars().all()
    products = (await db.execute(select(Product).where(Product.is_active.is_(True))
                                 .order_by(Product.is_popular.desc(), Product.id).limit(12))).scalars().all()
    promos = (await db.execute(select(Promotion).where(Promotion.is_active.is_(True)).limit(5))).scalars().all()
    return {
        "featured_games": [GameOut.model_validate(g).model_dump() for g in games],
        "popular_products": [ProductOut.model_validate(p).model_dump() for p in products],
        "promotions": [{"slug": p.slug, "title": p.title, "banner_url": p.banner_url} for p in promos],
    }
