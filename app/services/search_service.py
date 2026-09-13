"""Global search across games, products, listings, sellers."""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, MarketplaceListing, Product, Seller


async def global_search(db: AsyncSession, q: str, *, limit: int = 8) -> dict:
    q = (q or "").strip()
    if len(q) < 2:
        return {"games": [], "products": [], "listings": [], "sellers": []}
    like = f"%{q}%"
    games = (await db.execute(select(Game).where(Game.is_active.is_(True), Game.title.ilike(like)).limit(limit))).scalars().all()
    products = (await db.execute(select(Product).where(Product.is_active.is_(True), Product.name.ilike(like)).limit(limit))).scalars().all()
    listings = (await db.execute(select(MarketplaceListing).where(
        MarketplaceListing.status == "active",
        or_(MarketplaceListing.title.ilike(like), MarketplaceListing.description.ilike(like)),
    ).limit(limit))).scalars().all()
    sellers = (await db.execute(select(Seller).where(Seller.is_active.is_(True), Seller.shop_name.ilike(like)).limit(limit))).scalars().all()
    return {
        "games": [{"id": g.id, "slug": g.slug, "title": g.title, "logo": g.logo_url} for g in games],
        "products": [{"id": p.id, "game_id": p.game_id, "name": p.name, "price": str(p.selling_price)} for p in products],
        "listings": [{"id": l.id, "title": l.title, "price": str(l.price)} for l in listings],
        "sellers": [{"id": s.id, "shop_name": s.shop_name} for s in sellers],
    }
