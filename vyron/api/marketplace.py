"""Public marketplace API — browse approved listings, seller profiles, purchase."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import SellerListing, SellerProfile, User
from vyron.enums import ListingStatus, SellerStatus
from vyron.errors import NotFoundError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user
from vyron.security.sessions import client_ip
from vyron.services import seller_service
from vyron.web.serializers import listing_public, payment_public, seller_order_public, seller_public

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


@router.get("/listings")
def browse(
    db: DbSession = Depends(get_db),
    q: Optional[str] = Query(None, max_length=80),
    game_id: Optional[str] = Query(None),
    sort: str = Query("newest", pattern="^(newest|price_asc|price_desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    data = seller_service.browse_listings(db, query=q, game_id=game_id, sort=sort, page=page, page_size=page_size)
    return paginated([listing_public(l) for l in data["items"]], data["total"], page, page_size)


@router.get("/listings/{listing_id}")
def listing_detail(listing_id: str, db: DbSession = Depends(get_db)):
    listing = db.get(SellerListing, listing_id)
    if listing is None or listing.status != ListingStatus.APPROVED.value:
        raise NotFoundError("Listing not found.")
    listing.views = (listing.views or 0) + 1
    db.commit()
    return ok(listing_public(listing))


@router.get("/sellers/{username}")
def seller_detail(username: str, db: DbSession = Depends(get_db)):
    profile = (
        db.query(SellerProfile)
        .filter(SellerProfile.user.has(username=username.strip().lower()), SellerProfile.status == SellerStatus.ACTIVE.value)
        .first()
    )
    if profile is None:
        raise NotFoundError("Seller not found.")
    own = (
        db.query(SellerListing)
        .filter(SellerListing.seller_id == profile.id, SellerListing.status == ListingStatus.APPROVED.value)
        .order_by(SellerListing.is_promoted.desc(), SellerListing.created_at.desc())
        .limit(24)
        .all()
    )
    data = seller_public(profile)
    data["listings"] = [listing_public(l) for l in own]
    return ok(data)


@router.post("/listings/{listing_id}/purchase")
def purchase(
    listing_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
    db: DbSession = Depends(get_db),
    buyer: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "marketplace-purchase", "10/minute", user_id=buyer.id)
    seller_order, payment = seller_service.purchase_listing(
        db,
        buyer,
        listing_id,
        provider_name=payload.get("provider"),
        idempotency_key=str(payload.get("idempotency_key") or "")[:80] or None,
        ip_address=client_ip(request),
    )
    seller_profile = db.get(SellerProfile, seller_order.seller_id)
    return ok(
        {
            "order": seller_order_public(seller_order, viewer="buyer", seller_profile=seller_profile),
            "payment": payment_public(payment),
        },
        message_code="ORDER_CREATED",
    )
