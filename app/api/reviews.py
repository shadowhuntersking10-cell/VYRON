from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import MarketplaceListing, Order, OrderStatus, Review, Seller, User

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewIn(BaseModel):
    order_id: int
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


@router.post("")
async def create_review(data: ReviewIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    order = await db.get(Order, data.order_id)
    if not order or order.user_id != user.id or order.status != OrderStatus.COMPLETED:
        raise HTTPException(403, "review_not_allowed")
    await db.refresh(order, attribute_names=["items"])
    listing_id = next((i.listing_id for i in order.items if i.kind == "marketplace" and i.listing_id), None)
    if not listing_id:
        raise HTTPException(403, "review_not_allowed")
    existing = (await db.execute(select(Review).where(Review.order_id == order.id, Review.user_id == user.id))).scalars().first()
    if existing:
        raise HTTPException(400, "already_reviewed")
    listing = await db.get(MarketplaceListing, listing_id)
    review = Review(order_id=order.id, listing_id=listing_id,
                    seller_id=listing.seller_id if listing else None,
                    user_id=user.id, rating=data.rating, comment=data.comment)
    db.add(review)
    if listing:
        seller = await db.get(Seller, listing.seller_id)
        if seller:
            agg = (await db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(Review.seller_id == seller.id))).first()
            # include the new review (flush first)
            await db.flush()
            agg = (await db.execute(select(func.avg(Review.rating), func.count(Review.id)).where(Review.seller_id == seller.id))).first()
            seller.rating_avg = round(float(agg[0] or 0), 2)
            seller.rating_count = int(agg[1] or 0)
    await db.commit()
    return {"ok": True}


@router.get("/listing/{listing_id}")
async def listing_reviews(listing_id: int, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Review).where(Review.listing_id == listing_id).order_by(Review.id.desc()).limit(30))).scalars().all()
    return [{"rating": r.rating, "comment": r.comment, "created_at": r.created_at.isoformat()} for r in rows]
