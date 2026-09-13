"""Public products API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import models
from app.dependencies import Db

router = APIRouter(prefix="/api/products", tags=["products"])


def _out(p: models.Product) -> dict:
    return {"id": p.id, "game_id": p.game_id, "name": p.name, "slug": p.slug,
            "description": p.description, "category": p.category, "currency": p.currency,
            "price": str(p.customer_price), "old_price": str(p.old_price),
            "image": p.image, "popular": p.popular, "featured": p.featured,
            "stock": p.stock_status,
            "game": {"slug": p.game.slug, "name": p.game.name} if p.game else None}


@router.get("")
def list_products(db: Db, game_id: int | None = None, popular: bool | None = None,
                  featured: bool | None = None, search: str = "",
                  sort: str = "popular", page: int = 1, per_page: int = 24):
    q = db.query(models.Product).filter_by(status="active")
    if game_id:
        q = q.filter_by(game_id=game_id)
    if popular is not None:
        q = q.filter_by(popular=popular)
    if featured is not None:
        q = q.filter_by(featured=featured)
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    if sort == "price_asc":
        q = q.order_by(models.Product.customer_price)
    elif sort == "price_desc":
        q = q.order_by(models.Product.customer_price.desc())
    else:
        q = q.order_by(models.Product.popular.desc(), models.Product.sales_count.desc())
    total = q.count()
    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [_out(p) for p in items], "total": total, "page": page, "per_page": per_page}


@router.get("/{slug}")
def product_detail(slug: str, db: Db):
    p = db.query(models.Product).filter(
        ((models.Product.slug == slug) | (models.Product.id == slug)) if slug.isdigit() else (models.Product.slug == slug)
    ).first()
    if not p or p.status != "active":
        raise HTTPException(status_code=404, detail="product_not_found")
    out = _out(p)
    out["variants"] = [{"id": v.id, "name": v.name, "price_delta": str(v.price_delta)} for v in p.variants if v.status == "active"]
    return out
