"""Global search — games, products, marketplace listings, sellers (paginated)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from vyron.db.models import Game, Product, ProductVariant, SellerListing, SellerProfile
from vyron.enums import GameStatus, ListingStatus, SellerStatus


def global_search(db: DbSession, query: str, *, page: int = 1, page_size: int = 8) -> Dict[str, Any]:
    q = (query or "").strip()[:80]
    result: Dict[str, Any] = {"query": q, "games": [], "products": [], "listings": [], "sellers": []}
    if len(q) < 2:
        return result
    like = f"%{q}%"
    offset = (max(1, page) - 1) * page_size

    games = (
        db.query(Game)
        .filter(Game.status == GameStatus.ACTIVE.value, or_(Game.name.like(like), Game.slug.like(like)))
        .order_by(Game.sort_order)
        .offset(offset)
        .limit(page_size)
        .all()
    )
    result["games"] = [
        {"id": g.id, "name": g.name, "slug": g.slug, "logo_url": g.logo_url, "featured": g.is_featured} for g in games
    ]

    products = (
        db.query(Product)
        .filter(Product.active.is_(True), or_(Product.name.like(like), Product.description.like(like)))
        .order_by(Product.is_featured.desc(), Product.sort_order)
        .offset(offset)
        .limit(page_size)
        .all()
    )
    product_items = []
    for p in products:
        cheapest: Optional[ProductVariant] = (
            db.query(ProductVariant)
            .filter(ProductVariant.product_id == p.id, ProductVariant.active.is_(True))
            .order_by(ProductVariant.selling_price.asc())
            .first()
        )
        product_items.append(
            {
                "id": p.id,
                "name": p.name,
                "slug": p.slug,
                "type": p.type,
                "image_url": p.image_url,
                "game": p.game.name if p.game else None,
                "from_price": str(cheapest.selling_price) if cheapest else None,
                "currency": cheapest.currency if cheapest else "USD",
            }
        )
    result["products"] = product_items

    listings = (
        db.query(SellerListing)
        .filter(SellerListing.status == ListingStatus.APPROVED.value, SellerListing.title.like(like))
        .order_by(SellerListing.is_promoted.desc(), SellerListing.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    result["listings"] = [
        {
            "id": listing.id,
            "title": listing.title,
            "price": str(listing.price),
            "currency": listing.currency,
            "seller": listing.seller.display_name if listing.seller else "",
            "delivery_type": listing.delivery_type,
            "images": listing.images or [],
        }
        for listing in listings
    ]

    sellers = (
        db.query(SellerProfile)
        .filter(SellerProfile.status == SellerStatus.ACTIVE.value, SellerProfile.display_name.like(like))
        .order_by(SellerProfile.rating.desc(), SellerProfile.completed_orders.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    result["sellers"] = [
        {
            "id": s.id,
            "username": s.user.username if s.user else "",
            "display_name": s.display_name,
            "rating": str(s.rating),
            "completed_orders": s.completed_orders,
            "verified": s.verification_status == "VERIFIED",
            "avatar_url": s.avatar_url,
        }
        for s in sellers
    ]
    result["total"] = len(games) + len(product_items) + len(listings) + len(sellers)
    return result
