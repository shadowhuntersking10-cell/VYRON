from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import Product, Game
from typing import Optional

router = APIRouter(prefix="/api/products", tags=["products"])

@router.get("/")
async def list_products(
    db: AsyncSession = Depends(get_db),
    game_id: Optional[int] = Query(None),
    game_slug: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    featured: Optional[bool] = Query(None),
    popular: Optional[bool] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort: str = Query("popular", description="popular, price_asc, price_desc, newest"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = select(Product).where(Product.is_active == True)

    if game_id:
        query = query.where(Product.game_id == game_id)
    if game_slug:
        query = query.join(Game, Product.game_id == Game.id).where(Game.slug == game_slug)
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    if featured is not None:
        query = query.where(Product.featured == featured)
    if popular is not None:
        query = query.where(Product.popular == popular)
    if min_price is not None:
        query = query.where(Product.customer_price >= min_price)
    if max_price is not None:
        query = query.where(Product.customer_price <= max_price)

    # Sorting
    if sort == "price_asc":
        query = query.order_by(Product.customer_price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.customer_price.desc())
    elif sort == "newest":
        query = query.order_by(Product.created_at.desc())
    else:
        query = query.order_by(Product.popular.desc(), Product.featured.desc(), Product.sort_order)

    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    query = query.offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    products = result.scalars().all()

    # Get game info for each product (could optimize with join)
    items = []
    for p in products:
        game = None
        if p.game_id:
            g_result = await db.execute(select(Game).where(Game.id == p.game_id))
            game = g_result.scalar_one_or_none()
        
        discount = None
        if p.old_price and p.old_price > p.customer_price:
            discount = float((p.old_price - p.customer_price) / p.old_price * 100)

        items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "description": p.description,
            "game_id": p.game_id,
            "game_name": game.name if game else None,
            "game_slug": game.slug if game else None,
            "game_logo": game.logo_url if game else None,
            "customer_price": float(p.customer_price),
            "old_price": float(p.old_price) if p.old_price else None,
            "currency": p.currency,
            "image_url": p.image_url,
            "featured": p.featured,
            "popular": p.popular,
            "stock_status": p.stock_status,
            "discount_percent": round(discount, 1) if discount else None
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page -1)//per_page if total else 1
    }

@router.get("/{product_id}")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")

    game = None
    if product.game_id:
        g_result = await db.execute(select(Game).where(Game.id == product.game_id))
        game = g_result.scalar_one_or_none()

    # Pricing preview
    from app.services.pricing import PricingService
    pricing = PricingService.calculate_product_pricing(product.supplier_cost)

    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "game_id": product.game_id,
        "game": {"id": game.id, "name": game.name, "slug": game.slug, "logo_url": game.logo_url} if game else None,
        "customer_price": float(product.customer_price),
        "old_price": float(product.old_price) if product.old_price else None,
        "supplier_cost": float(product.supplier_cost),
        "currency": product.currency,
        "image_url": product.image_url,
        "featured": product.featured,
        "popular": product.popular,
        "stock_status": product.stock_status,
        "is_active": product.is_active,
        "pricing": pricing
    }

@router.get("/by-slug/{slug}")
async def get_product_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.slug == slug))
    product = result.scalar_one_or_none()
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    return await get_product(product.id, db)
