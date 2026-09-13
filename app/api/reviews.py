"""Reviews API (verified purchasers only)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app import models
from app.dependencies import Db, require_user
from app.schemas import ReviewIn

router = APIRouter(prefix="/api", tags=["reviews"])


@router.post("/listings/{listing_id}/reviews")
def create_review(listing_id: int, body: ReviewIn, request: Request, db: Db):
    user = require_user(request, db)
    listing = db.get(models.MarketplaceListing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="listing_not_found")
    order = db.query(models.Order).filter_by(id=body.order_id, user_id=user.id, status="COMPLETED").first()
    if not order:
        raise HTTPException(status_code=403, detail="purchase_required")
    item = db.query(models.OrderItem).filter_by(order_id=order.id, listing_id=listing_id).first()
    if not item:
        raise HTTPException(status_code=403, detail="purchase_required")
    if db.query(models.Review).filter_by(listing_id=listing_id, user_id=user.id, order_id=order.id).first():
        raise HTTPException(status_code=400, detail="already_reviewed")
    r = models.Review(listing_id=listing_id, user_id=user.id, order_id=order.id,
                      rating=body.rating, comment=body.comment[:2000])
    db.add(r)
    db.flush()
    # recompute aggregates
    all_r = db.query(models.Review).filter_by(listing_id=listing_id).all()
    listing.reviews_count = len(all_r)
    listing.rating = sum(x.rating for x in all_r) / len(all_r)
    seller = db.get(models.Seller, listing.seller_id)
    if seller:
        from sqlalchemy import func
        agg = db.query(func.avg(models.Review.rating)).join(
            models.MarketplaceListing, models.MarketplaceListing.id == models.Review.listing_id
        ).filter(models.MarketplaceListing.seller_id == seller.id).scalar()
        seller.rating = round(float(agg or 0), 2)
    db.commit()
    return {"ok": True, "id": r.id}
