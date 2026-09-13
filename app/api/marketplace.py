from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models import MarketplaceListing, Seller, User
from app.schemas import ListingOut, SellerOut
from app.services import marketplace_service

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class ListingIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str | None = None
    images: list[str] = []
    price: float = Field(ge=0)
    currency: str = "UZS"
    category: str = "other"
    delivery_type: str = "manual"
    stock: int = -1


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
    return [ListingOut.model_validate(r) for r in rows]


@router.get("/listings/{listing_id}", response_model=ListingOut)
async def listing_detail(listing_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(MarketplaceListing, listing_id)
    if not row or row.status == "deleted":
        raise HTTPException(404, "listing_not_found")
    row.views = (row.views or 0) + 1
    await db.commit()
    return row


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
    row = MarketplaceListing(
        seller_id=seller.id, title=data.title, description=data.description,
        images=data.images[:8], price=data.price, currency=data.currency,
        category=data.category, delivery_type=data.delivery_type, stock=data.stock, status="active",
    )
    db.add(row)
    await db.commit()
    return row


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
