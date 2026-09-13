from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import Game, GameCategory, Product
from typing import Optional

router = APIRouter(prefix="/api/games", tags=["games"])

@router.get("/")
async def list_games(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = select(Game).where(Game.status == "ACTIVE")
    
    if search:
        query = query.where(Game.name.ilike(f"%{search}%"))
    if featured is not None:
        query = query.where(Game.featured == featured)
    if category:
        # join category
        query = query.join(GameCategory, Game.category_id == GameCategory.id).where(GameCategory.slug == category)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    query = query.order_by(Game.sort_order, Game.featured.desc(), Game.name).offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    games = result.scalars().all()

    return {
        "items": [
            {
                "id": g.id,
                "name": g.name,
                "slug": g.slug,
                "description": g.short_description or g.description,
                "logo_url": g.logo_url,
                "cover_url": g.cover_url,
                "banner_url": g.banner_url,
                "featured": g.featured,
                "popular": g.popular,
                "status": g.status
            } for g in games
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page -1)//per_page if total else 1
    }

@router.get("/{slug}")
async def get_game(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Game).where(Game.slug == slug))
    game = result.scalar_one_or_none()
    if not game:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Game not found")
    
    # Get products count
    count_result = await db.execute(select(func.count(Product.id)).where(Product.game_id == game.id, Product.is_active == True))
    products_count = count_result.scalar()

    # Get fields
    from sqlalchemy.orm import selectinload
    result = await db.execute(select(Game).options(selectinload(Game.fields), selectinload(Game.category)).where(Game.id == game.id))
    game_full = result.scalar_one_or_none()

    return {
        "id": game.id,
        "name": game.name,
        "slug": game.slug,
        "description": game.description,
        "short_description": game.short_description,
        "logo_url": game.logo_url,
        "cover_url": game.cover_url,
        "banner_url": game.banner_url,
        "featured": game.featured,
        "popular": game.popular,
        "status": game.status,
        "seo_title": game.seo_title,
        "seo_description": game.seo_description,
        "products_count": products_count,
        "category": {"id": game_full.category.id, "name": game_full.category.name, "slug": game_full.category.slug} if game_full and game_full.category else None,
        "fields": [{"field_key": f.field_key, "label": f.label, "placeholder": f.placeholder, "field_type": f.field_type, "required": f.required} for f in (game_full.fields if game_full else [])]
    }

@router.get("/categories/list")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GameCategory).order_by(GameCategory.sort_order))
    cats = result.scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in cats]
