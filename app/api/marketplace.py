from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import MarketplaceListing, MarketplaceCategory, Seller, User
from app.dependencies import get_current_user_optional
from typing import Optional

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])

@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketplaceCategory).where(MarketplaceCategory.is_active == True).order_by(MarketplaceCategory.sort_order))
    cats = result.scalars().all()
    return [{"id": c.id, "name": c.name, "slug": c.slug, "commission_rate": float(c.commission_rate)} for c in cats]

@router.get("/listings")
async def list_listings(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    seller_id: Optional[int] = Query(None),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = select(MarketplaceListing).where(MarketplaceListing.status == "ACTIVE")

    if search:
        query = query.where(MarketplaceListing.title.ilike(f"%{search}%"))
    if category:
        query = query.join(MarketplaceCategory, MarketplaceListing.category_id == MarketplaceCategory.id).where(MarketplaceCategory.slug == category)
    if min_price is not None:
        query = query.where(MarketplaceListing.price >= min_price)
    if max_price is not None:
        query = query.where(MarketplaceListing.price <= max_price)
    if seller_id:
        query = query.where(MarketplaceListing.seller_id == seller_id)

    if sort == "price_asc":
        query = query.order_by(MarketplaceListing.price.asc())
    elif sort == "price_desc":
        query = query.order_by(MarketplaceListing.price.desc())
    elif sort == "popular":
        query = query.order_by(MarketplaceListing.sales_count.desc(), MarketplaceListing.view_count.desc())
    else:
        query = query.order_by(MarketplaceListing.created_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    listings = result.scalars().all()

    items = []
    for lst in listings:
        # Get seller
        seller = None
        if lst.seller_id:
            s_res = await db.execute(select(Seller).where(Seller.id == lst.seller_id))
            seller = s_res.scalar_one_or_none()

        items.append({
            "id": lst.id,
            "title": lst.title,
            "slug": lst.slug,
            "price": float(lst.price),
            "old_price": float(lst.old_price) if lst.old_price else None,
            "currency": lst.currency,
            "stock": lst.stock,
            "rating": float(lst.rating),
            "sales_count": lst.sales_count,
            "seller": {"id": seller.id, "shop_name": seller.shop_name, "shop_slug": seller.shop_slug} if seller else None
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page -1)//per_page if total else 1
    }

@router.get("/listings/{listing_id}")
async def get_listing(listing_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MarketplaceListing).where(MarketplaceListing.id == listing_id))
    listing = result.scalar_one_or_none()
    if not listing:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Listing not found")

    # Increment view
    listing.view_count += 1
    await db.commit()

    seller = None
    if listing.seller_id:
        s_res = await db.execute(select(Seller).where(Seller.id == listing.seller_id))
        seller = s_res.scalar_one_or_none()

    # Get images
    from app.models.models import MarketplaceListingImage
    img_res = await db.execute(select(MarketplaceListingImage).where(MarketplaceListingImage.listing_id == listing.id).order_by(MarketplaceListingImage.sort_order))
    images = img_res.scalars().all()

    return {
        "id": listing.id,
        "title": listing.title,
        "slug": listing.slug,
        "description": listing.description,
        "price": float(listing.price),
        "old_price": float(listing.old_price) if listing.old_price else None,
        "currency": listing.currency,
        "stock": listing.stock,
        "status": listing.status,
        "rating": float(listing.rating),
        "view_count": listing.view_count,
        "sales_count": listing.sales_count,
        "seller": {"id": seller.id, "shop_name": seller.shop_name, "shop_slug": seller.shop_slug, "is_verified": seller.is_verified, "rating": float(seller.rating)} if seller else None,
        "images": [{"id": img.id, "url": img.image_url, "is_primary": img.is_primary} for img in images]
    }
