"""Read-model service for SSR pages (home, catalog, marketplace, donations).

Returns serializer-ready dicts; only public data (never supplier cost,
never inactive entities).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from vyron.db.models import Donation, DonationPage, Game, Product, SellerListing, SellerProfile, User
from vyron.enums import DonationStatus, GameStatus, ListingStatus, SellerStatus
from vyron.errors import NotFoundError
from vyron.money import to_money
from vyron.web import serializers as S


def _active_games(db: DbSession):
    return db.query(Game).filter(Game.status == GameStatus.ACTIVE.value).order_by(Game.sort_order, Game.name).all()


def home_payload(db: DbSession) -> Dict[str, Any]:
    featured_games = (
        db.query(Game)
        .filter(Game.status == GameStatus.ACTIVE.value, Game.is_featured.is_(True))
        .order_by(Game.sort_order)
        .limit(8)
        .all()
    )
    if not featured_games:
        featured_games = _active_games(db)[:8]
    featured_products = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.active.is_(True), Product.is_featured.is_(True))
        .order_by(Product.sort_order)
        .limit(8)
        .all()
    )
    if not featured_products:
        featured_products = (
            db.query(Product)
            .options(joinedload(Product.variants))
            .filter(Product.active.is_(True))
            .order_by(Product.sort_order)
            .limit(8)
            .all()
        )
    promoted_listings = (
        db.query(SellerListing)
        .filter(SellerListing.status == ListingStatus.APPROVED.value, SellerListing.is_promoted.is_(True))
        .order_by(SellerListing.created_at.desc())
        .limit(4)
        .all()
    )
    top_creators = (
        db.query(DonationPage, func.coalesce(func.sum(Donation.amount), 0).label("raised"))
        .join(Donation, Donation.page_id == DonationPage.id)
        .filter(DonationPage.active.is_(True), Donation.status == DonationStatus.COMPLETED.value)
        .group_by(DonationPage.id)
        .order_by(func.sum(Donation.amount).desc())
        .limit(3)
        .all()
    )
    creators = []
    for page, raised in top_creators:
        owner = db.get(User, page.user_id)
        if owner is None:
            continue
        creators.append(
            {
                "username": owner.username,
                "name": owner.name,
                "avatar_url": owner.avatar_url or page.avatar_url,
                "title": page.title,
                "raised": str(to_money(raised)),
                "goal": str(to_money(page.goal_amount)) if page.goal_amount else None,
                "currency": page.currency,
            }
        )
    stats = {
        "games": db.query(func.count(Game.id)).filter(Game.status == GameStatus.ACTIVE.value).scalar() or 0,
        "products": db.query(func.count(Product.id)).filter(Product.active.is_(True)).scalar() or 0,
        "sellers": db.query(func.count(SellerProfile.id)).filter(SellerProfile.status == SellerStatus.ACTIVE.value).scalar() or 0,
        "donations": db.query(func.count(Donation.id)).filter(Donation.status == DonationStatus.COMPLETED.value).scalar() or 0,
    }
    return {
        "featured_games": [S.game_public(g) for g in featured_games],
        "featured_products": [S.product_public(p) for p in featured_products],
        "promoted_listings": [S.listing_public(l) for l in promoted_listings],
        "top_creators": creators,
        "stats": stats,
    }


def all_games(db: DbSession) -> List[Dict[str, Any]]:
    return [S.game_public(g) for g in _active_games(db)]


def game_detail(db: DbSession, slug: str) -> Dict[str, Any]:
    game = db.query(Game).filter(Game.slug == slug, Game.status == GameStatus.ACTIVE.value).first()
    if game is None:
        raise NotFoundError("Game not found.")
    products = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.game_id == game.id, Product.active.is_(True))
        .order_by(Product.is_featured.desc(), Product.sort_order, Product.name)
        .all()
    )
    return {"game": S.game_public(game), "products": [S.product_public(p) for p in products]}


def products_page(db: DbSession, game_slug: Optional[str] = None, query: Optional[str] = None) -> Dict[str, Any]:
    games = _active_games(db)
    q = db.query(Product).options(joinedload(Product.variants)).filter(Product.active.is_(True))
    active_game = None
    if game_slug:
        active_game = db.query(Game).filter(Game.slug == game_slug).first()
        if active_game:
            q = q.filter(Product.game_id == active_game.id)
    if query:
        like = f"%{query.strip()[:60]}%"
        q = q.filter(Product.name.like(like) | Product.description.like(like))
    products = q.order_by(Product.is_featured.desc(), Product.sort_order, Product.name).limit(60).all()
    return {
        "games": [S.game_public(g) for g in games],
        "active_game": S.game_public(active_game) if active_game else None,
        "products": [S.product_public(p) for p in products],
        "query": query or "",
    }


def product_detail(db: DbSession, slug: str) -> Dict[str, Any]:
    product = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.slug == slug, Product.active.is_(True))
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found.")
    related: List[Product] = []
    if product.game_id:
        related = (
            db.query(Product)
            .options(joinedload(Product.variants))
            .filter(Product.game_id == product.game_id, Product.active.is_(True), Product.id != product.id)
            .limit(4)
            .all()
        )
    return {"product": S.product_public(product), "related": [S.product_public(p) for p in related]}


def marketplace_page(db: DbSession) -> Dict[str, Any]:
    listings = (
        db.query(SellerListing)
        .filter(SellerListing.status == ListingStatus.APPROVED.value)
        .order_by(SellerListing.is_promoted.desc(), SellerListing.created_at.desc())
        .limit(48)
        .all()
    )
    return {"listings": [S.listing_public(l) for l in listings], "games": [S.game_public(g) for g in _active_games(db)]}


def listing_detail(db: DbSession, listing_id: str) -> Dict[str, Any]:
    listing = db.get(SellerListing, listing_id)
    if listing is None or listing.status != ListingStatus.APPROVED.value:
        raise NotFoundError("Listing not found.")
    listing.views = (listing.views or 0) + 1
    db.commit()
    seller = db.get(SellerProfile, listing.seller_id)
    similar = (
        db.query(SellerListing)
        .filter(
            SellerListing.status == ListingStatus.APPROVED.value,
            SellerListing.id != listing.id,
            SellerListing.game_id == listing.game_id if listing.game_id else SellerListing.is_promoted.is_(True),
        )
        .limit(4)
        .all()
    )
    return {
        "listing": S.listing_public(listing),
        "seller": S.seller_public(seller) if seller else None,
        "similar": [S.listing_public(l) for l in similar],
    }


def seller_profile_page(db: DbSession, username: str) -> Dict[str, Any]:
    profile = (
        db.query(SellerProfile)
        .filter(SellerProfile.user.has(username=username.strip().lower()), SellerProfile.status == SellerStatus.ACTIVE.value)
        .first()
    )
    if profile is None:
        raise NotFoundError("Seller not found.")
    listings = (
        db.query(SellerListing)
        .filter(SellerListing.seller_id == profile.id, SellerListing.status == ListingStatus.APPROVED.value)
        .order_by(SellerListing.is_promoted.desc(), SellerListing.created_at.desc())
        .limit(48)
        .all()
    )
    return {"seller": S.seller_public(profile), "listings": [S.listing_public(l) for l in listings]}


def promotions_page(db: DbSession) -> Dict[str, Any]:
    listings = (
        db.query(SellerListing)
        .filter(SellerListing.status == ListingStatus.APPROVED.value, SellerListing.is_promoted.is_(True))
        .order_by(SellerListing.created_at.desc())
        .limit(24)
        .all()
    )
    products = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.active.is_(True), Product.is_featured.is_(True))
        .limit(12)
        .all()
    )
    return {"listings": [S.listing_public(l) for l in listings], "products": [S.product_public(p) for p in products]}


def donations_index(db: DbSession, query: Optional[str] = None) -> List[Dict[str, Any]]:
    pages = (
        db.query(DonationPage)
        .filter(DonationPage.active.is_(True))
        .order_by(DonationPage.created_at.desc())
        .limit(60)
        .all()
    )
    creators = []
    for page in pages:
        owner = db.get(User, page.user_id)
        if owner is None or owner.status != "ACTIVE":
            continue
        if query:
            term = query.strip().lower()
            if term not in owner.username.lower() and term not in (owner.name or "").lower() and term not in (page.title or "").lower():
                continue
        raised = (
            db.query(func.coalesce(func.sum(Donation.amount), 0))
            .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value)
            .scalar()
        )
        creators.append(
            {
                "username": owner.username,
                "name": owner.name,
                "avatar_url": owner.avatar_url or page.avatar_url,
                "title": page.title,
                "description": (page.description or "")[:140],
                "raised": str(to_money(raised)),
                "goal": str(to_money(page.goal_amount)) if page.goal_amount else None,
                "currency": page.currency,
            }
        )
    return creators
