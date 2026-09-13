from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.dependencies import get_current_user
from app.models.models import Review, User, Order, MarketplaceListing
from typing import List

router = APIRouter(prefix="/api/reviews", tags=["reviews"])

@router.get("/listing/{listing_id}")
async def get_reviews(listing_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Review).where(Review.listing_id == listing_id).order_by(Review.created_at.desc()))
    reviews = result.scalars().all()
    return [{"id": r.id, "rating": r.rating, "comment": r.comment, "is_verified": r.is_verified_purchase, "created_at": r.created_at.isoformat()} for r in reviews]

@router.post("/listing/{listing_id}")
async def create_review(
    listing_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    rating = payload.get("rating")
    comment = payload.get("comment")

    if not rating or not (1 <= int(rating) <= 5):
        raise HTTPException(status_code=400, detail="Rating must be 1-5")

    # Check if user purchased
    result = await db.execute(select(Order).where(Order.user_id == current_user.id))
    orders = result.scalars().all()
    # Simplified check - in real system check order items for this listing
    is_verified = len(orders) > 0

    # Check duplicate
    result = await db.execute(select(Review).where(Review.user_id == current_user.id, Review.listing_id == listing_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You have already reviewed this listing")

    review = Review(
        user_id=current_user.id,
        listing_id=listing_id,
        rating=int(rating),
        comment=comment,
        is_verified_purchase=is_verified
    )
    db.add(review)
    await db.commit()

    return {"success": True, "review": {"id": review.id, "rating": review.rating}}
