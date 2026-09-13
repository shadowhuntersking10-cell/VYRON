from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models import ListingImage, MarketplaceCategory, MarketplaceListing, Seller, User
from app.schemas import ListingOut, SellerOut
from app.services import marketplace_service

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


async def _with_gallery(db: AsyncSession, rows: list[MarketplaceListing]) -> list[ListingOut]:
    ids = [r.id for r in rows]
    images: dict[int, list] = {}
    if ids:
        img_rows = (await db.execute(select(ListingImage)
                                     .where(ListingImage.listing_id.in_(ids))
                                     .order_by(ListingImage.sort_order))).scalars().all()
        for im in img_rows:
            images.setdefault(im.listing_id, []).append(
                {"id": im.id, "url": im.url, "alt_text": im.alt_text})
    out = []
    for r in rows:
        # Column values only: never touch lazy relationships in async context.
        data = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        payload = ListingOut.model_validate(data)
        payload.gallery = images.get(r.id, [])
        out.append(payload)
    return out


class ListingIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    images: list[str] = Field(default_factory=list, max_length=8)
    price: float = Field(ge=0)
    currency: str = "UZS"
    category: str = "other"
    delivery_type: str = "manual"
    stock: int = -1


@router.get("/categories")
async def marketplace_categories(db: AsyncSession = Depends(get_db)):
    from app.models import MarketplaceCategory
    from app.services import settings_service
    detailed = (await db.execute(select(MarketplaceCategory)
                                 .where(MarketplaceCategory.is_active == True)  # noqa: E712
                                 .order_by(MarketplaceCategory.sort_order))).scalars().all()
    if detailed:
        return {"categories": [c.slug for c in detailed],
                "detailed": [{"slug": c.slug, "name_uz": c.name_uz, "name_en": c.name_en,
                              "name_ru": c.name_ru, "icon": c.icon,
                              "commission_percent": str(c.commission_percent) if c.commission_percent is not None else None}
                             for c in detailed]}
    return {"categories": await settings_service.marketplace_category_slugs(db), "detailed": []}


@router.get("/listings", response_model=list[ListingOut])
async def listings(
    q: str = "", category: str = "", sort: str = "new",
    page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MarketplaceListing).where(MarketplaceListing.status == "active")
    if category:
        stmt = stmt.where(MarketplaceListing.category == category)
    if q:
        stmt = stmt.where(MarketplaceListing.title.ilike(f"%{q}%"))
    if sort == "price_asc":
        stmt = stmt.order_by(MarketplaceListing.price)
    elif sort == "price_desc":
        stmt = stmt.order_by(MarketplaceListing.price.desc())
    else:
        stmt = stmt.order_by(MarketplaceListing.is_promoted.desc(), MarketplaceListing.id.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()
    return await _with_gallery(db, list(rows))


@router.get("/listings/{listing_id}", response_model=ListingOut)
async def listing_detail(listing_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(MarketplaceListing, listing_id)
    if not row or row.status == "deleted":
        raise HTTPException(404, "listing_not_found")
    row.views = (row.views or 0) + 1
    await db.commit()
    return (await _with_gallery(db, [row]))[0]


@router.get("/sellers/{seller_id}", response_model=SellerOut)
async def seller_detail(seller_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(Seller, seller_id)
    if not row:
        raise HTTPException(404, "seller_not_found")
    return row


@router.post("/listings", response_model=ListingOut)
async def create_listing(data: ListingIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    seller = await marketplace_service.get_seller_for_user(db, user.id)
    if not seller:
        raise HTTPException(403, "seller_required")
    from app.services import settings_service
    allowed = await settings_service.marketplace_category_slugs(db)
    category = data.category if data.category in allowed else (allowed[0] if allowed else "other")
    cat_id = None
    if category:
        cat = (await db.execute(select(MarketplaceCategory)
                                .where(MarketplaceCategory.slug == category))).scalars().first()
        cat_id = cat.id if cat else None
    row = MarketplaceListing(
        seller_id=seller.id, title=data.title, description=data.description,
        images=data.images[:8], price=data.price, currency=data.currency,
        category=category, category_id=cat_id,
        delivery_type=data.delivery_type, stock=data.stock, status="active",
    )
    db.add(row)
    await db.flush()
    for i, url in enumerate(data.images[:8]):
        db.add(ListingImage(listing_id=row.id, url=url, alt_text=data.title, sort_order=i))
    await db.commit()
    return (await _with_gallery(db, [row]))[0]


@router.patch("/listings/{listing_id}", response_model=ListingOut)
async def update_listing(listing_id: int, data: ListingIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.get(MarketplaceListing, listing_id)
    seller = await marketplace_service.get_seller_for_user(db, user.id)
    if not row or not seller or row.seller_id != seller.id:
        raise HTTPException(404, "listing_not_found")
    for field in ("title", "description", "images", "price", "currency", "category", "delivery_type", "stock"):
        setattr(row, field, getattr(data, field))
    await db.commit()
    return row


@router.post("/listings/{listing_id}/status")
async def set_status(listing_id: int, status: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if status not in ("active", "paused", "sold", "deleted"):
        raise HTTPException(400, "bad_status")
    row = await db.get(MarketplaceListing, listing_id)
    seller = await marketplace_service.get_seller_for_user(db, user.id)
    if not row or not seller or row.seller_id != seller.id:
        raise HTTPException(404, "listing_not_found")
    row.status = status
    await db.commit()
    return {"ok": True, "status": status}


@router.post("/become-seller", response_model=SellerOut)
async def become_seller(
    shop_name: str, description: str | None = None,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _opt: User | None = Depends(get_current_user_optional),
):
    seller = await marketplace_service.become_seller(db, user, shop_name, description)
    await db.commit()
    return seller
