"""Marketplace: categories, listings, sellers, payouts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import models
from app.auth.service import grant_role
from app.config import settings
from app.dependencies import Db, require_seller, require_user
from app.schemas import ListingIn
from app.services import ledger, marketplace_svc as ms
from app.services.pricing import q
from app.utils.security import new_token

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


def _listing_out(l: models.MarketplaceListing) -> dict:
    seller = None
    if l.seller_id:
        s = db_get_seller(l)
        seller = {"shop": s.shop_name, "slug": s.slug, "rating": str(s.rating)} if s else None
    return {"id": l.id, "title": l.title, "slug": l.slug, "description": l.description,
            "price": str(l.price), "currency": l.currency, "stock": l.stock,
            "status": l.status, "featured": l.featured, "rating": str(l.rating),
            "reviews": l.reviews_count, "sales": l.sales_count, "seller": seller,
            "images": [i.url for i in sorted(l.images, key=lambda x: x.sort_order)]}


def db_get_seller(l):
    from app.database import SessionLocal
    # l is already attached; use its session via seller query on same session
    return None


@router.get("/categories")
def categories(db: Db):
    cats = db.query(models.MarketplaceCategory).filter_by(is_active=True).all()
    return {"items": [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in cats]}


@router.get("/listings")
def listings(db: Db, category_id: int | None = None, search: str = "", sort: str = "popular",
             min_price: float | None = None, max_price: float | None = None,
             page: int = 1, per_page: int = 24):
    query = db.query(models.MarketplaceListing).filter_by(status="active")
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        query = query.filter(models.MarketplaceListing.title.ilike(f"%{search}%"))
    if min_price is not None:
        query = query.filter(models.MarketplaceListing.price >= min_price)
    if max_price is not None:
        query = query.filter(models.MarketplaceListing.price <= max_price)
    if sort == "price_asc":
        query = query.order_by(models.MarketplaceListing.price)
    elif sort == "price_desc":
        query = query.order_by(models.MarketplaceListing.price.desc())
    elif sort == "rating":
        query = query.order_by(models.MarketplaceListing.rating.desc())
    else:
        query = query.order_by(models.MarketplaceListing.featured.desc(), models.MarketplaceListing.sales_count.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    out = []
    for l in items:
        d = _listing_out(l)
        s = db.get(models.Seller, l.seller_id) if l.seller_id else None
        d["seller"] = {"shop": s.shop_name, "slug": s.slug, "rating": str(s.rating)} if s else None
        out.append(d)
    return {"items": out, "total": total, "page": page, "per_page": per_page}


@router.get("/listings/{slug}")
def listing_detail(slug: str, db: Db):
    l = db.query(models.MarketplaceListing).filter(
        (models.MarketplaceListing.slug == slug) | (models.MarketplaceListing.id == slug)
        if slug.isdigit() else (models.MarketplaceListing.slug == slug)).first()
    if not l:
        raise HTTPException(status_code=404, detail="listing_not_found")
    d = _listing_out(l)
    s = db.get(models.Seller, l.seller_id) if l.seller_id else None
    d["seller"] = {"shop": s.shop_name, "slug": s.slug, "rating": str(s.rating), "sales": s.sales_count} if s else None
    reviews = db.query(models.Review).filter_by(listing_id=l.id).order_by(models.Review.id.desc()).limit(10).all()
    d["recent_reviews"] = [{"user": db.get(models.User, r.user_id).username if db.get(models.User, r.user_id) else "?",
                            "rating": r.rating, "comment": r.comment} for r in reviews]
    return d


class SellerRegister(BaseModel):
    shop_name: str
    bio: str = ""


@router.post("/sellers/register")
def seller_register(body: SellerRegister, request: Request, db: Db):
    user = require_user(request, db)
    if db.query(models.Seller).filter_by(user_id=user.id).first():
        raise HTTPException(status_code=400, detail="already_seller")
    slug = "".join(c.lower() if c.isalnum() else "-" for c in body.shop_name)[:60].strip("-") or f"shop-{user.id}"
    if db.query(models.Seller).filter_by(slug=slug).first():
        slug = f"{slug}-{user.id}"
    seller = models.Seller(user_id=user.id, shop_name=body.shop_name[:128], slug=slug,
                           bio=body.bio[:2000], status="pending")
    db.add(seller)
    db.flush()
    db.add(models.SellerBalance(seller_id=seller.id))
    grant_role(db, user, "seller")
    db.commit()
    return {"ok": True, "status": seller.status, "slug": seller.slug}


@router.get("/sellers/me")
def seller_me(request: Request, db: Db):
    user = require_seller(request, db)
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="not_seller")
    bal = ms.get_balance(db, seller.id)
    db.commit()
    listings = db.query(models.MarketplaceListing).filter_by(seller_id=seller.id).order_by(
        models.MarketplaceListing.id.desc()).limit(50).all()
    return {"seller": {"shop": seller.shop_name, "slug": seller.slug, "status": seller.status,
                       "rating": str(seller.rating), "sales": seller.sales_count},
            "balance": {"available": str(bal.available), "pending": str(bal.pending),
                        "lifetime": str(bal.lifetime_earned)},
            "listings": [_listing_out(l) for l in listings]}


@router.post("/sellers/listings")
def seller_create_listing(body: ListingIn, request: Request, db: Db):
    user = require_seller(request, db)
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    if not seller or seller.status != "approved":
        raise HTTPException(status_code=403, detail="seller_not_approved")
    slug = "".join(c.lower() if c.isalnum() else "-" for c in body.title)[:80].strip("-")
    slug = f"{slug}-{new_token(4).lower()}" or f"listing-{new_token(4)}"
    l = models.MarketplaceListing(seller_id=seller.id, category_id=body.category_id,
                                 title=body.title, slug=slug, description=body.description,
                                 price=q(body.price), stock=max(0, body.stock), status="active")
    db.add(l)
    db.commit()
    return {"ok": True, "id": l.id, "slug": l.slug}


@router.patch("/sellers/listings/{listing_id}")
def seller_update_listing(listing_id: int, body: ListingIn, request: Request, db: Db):
    user = require_seller(request, db)
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    l = db.get(models.MarketplaceListing, listing_id)
    if not l or not seller or l.seller_id != seller.id:
        raise HTTPException(status_code=404, detail="listing_not_found")
    l.title = body.title
    l.description = body.description
    l.price = q(body.price)
    l.stock = max(0, body.stock)
    if body.category_id:
        l.category_id = body.category_id
    db.commit()
    return {"ok": True}


@router.post("/sellers/listings/{listing_id}/pause")
def seller_pause_listing(listing_id: int, request: Request, db: Db):
    user = require_seller(request, db)
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    l = db.get(models.MarketplaceListing, listing_id)
    if not l or not seller or l.seller_id != seller.id:
        raise HTTPException(status_code=404, detail="listing_not_found")
    l.status = "paused" if l.status == "active" else "active"
    db.commit()
    return {"ok": True, "status": l.status}


class PayoutIn(BaseModel):
    amount: float
    method: str = ""
    details: str = ""


@router.post("/sellers/payouts")
def request_payout(body: PayoutIn, request: Request, db: Db):
    user = require_seller(request, db)
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    bal = ms.get_balance(db, seller.id)
    amount = q(body.amount)
    if amount <= 0 or amount > q(bal.available):
        raise HTTPException(status_code=400, detail="invalid_payout_amount")
    bal.available = q(bal.available) - amount
    p = models.SellerPayout(seller_id=seller.id, amount=amount, method=body.method[:64],
                            details=body.details[:500], status="pending")
    db.add(p)
    db.commit()
    return {"ok": True, "payout_id": p.id}
