"""Seller area API — profile, listings, orders, balance, payouts, promotions, subscription."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import (
    PayoutRequest,
    SellerBalanceTransaction,
    SellerListing,
    SellerOrder,
    SellerSubscriptionPlan,
    User,
)
from vyron.enums import ListingStatus, UserRole
from vyron.errors import ConflictError, NotFoundError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user, require_roles
from vyron.services import seller_service, settings_service
from vyron.web.serializers import (
    balance_public,
    listing_public,
    payment_public,
    payout_public,
    seller_order_public,
    seller_public,
)

router = APIRouter(prefix="/api/seller", tags=["seller"])

_seller_dep = require_roles(UserRole.SELLER, UserRole.ADMIN, UserRole.SUPER_ADMIN)


@router.post("/apply")
def apply(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    enforce_rate_limit(request, "seller-apply", "3/hour", user_id=user.id)
    profile = seller_service.become_seller(db, user, str(payload.get("display_name") or user.name), payload.get("description"))
    return ok(seller_public(profile), message_code="SELLER_CREATED")


@router.get("/me")
def me(db: DbSession = Depends(get_db), user: User = Depends(_seller_dep)):
    profile = seller_service.get_profile(db, user)
    balance = seller_service.get_balance(db, profile.id)
    commission = profile.commission_override_pct
    if commission is None:
        commission = settings_service.marketplace_commission_pct(db)
    data = seller_public(profile)
    data.update(
        {
            "status": profile.status,
            "balance": balance_public(balance),
            "holding_hours": settings_service.holding_period_hours(db),
            "commission_pct": str(commission),
            "min_payout": str(settings_service.min_payout_amount(db)),
        }
    )
    return ok(data)


@router.put("/me")
def update_me(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    seller_service.update_profile(
        db, profile,
        display_name=payload.get("display_name"),
        description=payload.get("description"),
        avatar_url=payload.get("avatar_url"),
    )
    return ok(seller_public(profile))


# --- listings ------------------------------------------------------------------------
@router.get("/listings")
def listings(
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    profile = seller_service.get_profile(db, user)
    query = db.query(SellerListing).filter(SellerListing.seller_id == profile.id)
    if status:
        query = query.filter(SellerListing.status == status.upper())
    total = query.count()
    items = query.order_by(SellerListing.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    data = [listing_public(l) for l in items]
    for entry, raw in zip(data, items):
        entry["has_delivery_data"] = bool(raw.sensitive_delivery_data_enc)
    return paginated(data, total, page, page_size)


@router.post("/listings")
def create_listing(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    listing = seller_service.create_listing(
        db, profile,
        title=str(payload.get("title", "")),
        description=payload.get("description"),
        price=Decimal(str(payload.get("price", "0"))),
        currency=str(payload.get("currency", "USD")),
        game_id=payload.get("game_id"),
        delivery_type=str(payload.get("delivery_type", "MANUAL")),
        images=payload.get("images") or [],
        sensitive_delivery_data=payload.get("sensitive_delivery_data"),
        submit_for_review=bool(payload.get("submit_for_review", False)),
    )
    return ok(listing_public(listing), message_code="LISTING_CREATED")


@router.put("/listings/{listing_id}")
def update_listing(
    listing_id: str,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    listing = seller_service.update_listing(db, profile, listing_id, **payload)
    return ok(listing_public(listing))


@router.post("/listings/{listing_id}/submit")
def submit_listing(
    listing_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    listing = seller_service.submit_listing(db, profile, listing_id)
    return ok(listing_public(listing), message_code="LISTING_SUBMITTED")


@router.delete("/listings/{listing_id}")
def delete_listing(
    listing_id: str,
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    listing = db.query(SellerListing).filter(SellerListing.id == listing_id, SellerListing.seller_id == profile.id).first()
    if listing is None:
        raise NotFoundError("Listing not found.")
    if listing.status in {ListingStatus.SOLD.value, ListingStatus.PENDING_REVIEW.value}:
        raise ConflictError("Sold or in-review listings cannot be deleted.", code="LISTING_LOCKED")
    has_orders = db.query(SellerOrder).filter(SellerOrder.listing_id == listing.id).first() is not None
    if has_orders:
        listing.status = ListingStatus.SUSPENDED.value
        listing.is_promoted = False
        db.commit()
        return ok(message_code="LISTING_SUSPENDED")
    db.delete(listing)
    db.commit()
    return ok(message_code="LISTING_DELETED")


# --- orders ---------------------------------------------------------------------------
@router.get("/orders")
def orders(
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    profile = seller_service.get_profile(db, user)
    query = db.query(SellerOrder).filter(SellerOrder.seller_id == profile.id)
    if status:
        query = query.filter(SellerOrder.status == status.upper())
    total = query.count()
    items = query.order_by(SellerOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([seller_order_public(o, viewer="seller") for o in items], total, page, page_size)


@router.post("/orders/{order_id}/delivered")
def mark_delivered(
    order_id: str,
    payload: Dict[str, Any] = Body(default={}),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    order = db.query(SellerOrder).filter(SellerOrder.id == order_id, SellerOrder.seller_id == profile.id).first()
    if order is None:
        raise NotFoundError("Order not found.")
    seller_service.mark_delivered(db, order, profile, payload.get("note"))
    return ok(seller_order_public(order, viewer="seller"), message_code="ORDER_DELIVERED")


# --- balance & payouts ------------------------------------------------------------------
@router.get("/balance/transactions")
def balance_transactions(
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    profile = seller_service.get_profile(db, user)
    query = db.query(SellerBalanceTransaction).filter(SellerBalanceTransaction.seller_id == profile.id)
    total = query.count()
    txs = query.order_by(SellerBalanceTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [
            {
                "id": tx.id,
                "type": tx.type,
                "pending_delta": str(tx.pending_delta),
                "available_delta": str(tx.available_delta),
                "reserved_delta": str(tx.reserved_delta),
                "note": tx.note,
                "available_at": tx.available_at.isoformat() if tx.available_at else None,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in txs
        ],
        total, page, page_size,
    )


@router.post("/payouts")
def request_payout(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    enforce_rate_limit(request, "payout", "3/hour", user_id=user.id)
    profile = seller_service.get_profile(db, user)
    payout = seller_service.request_payout(
        db, profile,
        amount=Decimal(str(payload.get("amount", "0"))),
        method=str(payload.get("method", "CARD")),
        details=str(payload.get("details", "")),
        idempotency_key=str(payload.get("idempotency_key") or "")[:80] or None,
    )
    return ok(payout_public(payout), message_code="PAYOUT_REQUESTED")


@router.get("/payouts")
def list_payouts(
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    profile = seller_service.get_profile(db, user)
    query = db.query(PayoutRequest).filter(PayoutRequest.seller_id == profile.id)
    total = query.count()
    items = query.order_by(PayoutRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([payout_public(p) for p in items], total, page, page_size)


# --- promotions & subscription -------------------------------------------------------------
@router.post("/promotions")
def buy_promotion(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    promo, payment = seller_service.purchase_promotion(
        db, profile, str(payload.get("listing_id", "")), str(payload.get("kind", "FEATURED")),
        provider_name=payload.get("provider"),
    )
    return ok({"promotion_id": promo.id, "kind": promo.kind, "price": str(promo.price), "payment": payment_public(payment)})


@router.get("/subscription/plans")
def plans(db: DbSession = Depends(get_db), user: User = Depends(_seller_dep)):
    rows = db.query(SellerSubscriptionPlan).filter(SellerSubscriptionPlan.active.is_(True)).order_by(SellerSubscriptionPlan.price).all()
    return ok(
        [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "price": str(p.price),
                "currency": p.currency,
                "period_days": p.period_days,
                "features": p.features or [],
            }
            for p in rows
        ]
    )


@router.post("/subscription")
def subscribe(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(_seller_dep),
):
    profile = seller_service.get_profile(db, user)
    subscription, payment = seller_service.subscribe(db, profile, str(payload.get("plan_code", "")), provider_name=payload.get("provider"))
    return ok({"subscription_id": subscription.id, "payment": payment_public(payment)})
