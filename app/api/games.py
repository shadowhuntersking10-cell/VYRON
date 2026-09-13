"""Public game catalog API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import models
from app.dependencies import Db

router = APIRouter(prefix="/api/games", tags=["games"])


def _game_out(g: models.Game) -> dict:
    return {"id": g.id, "name": g.name, "slug": g.slug, "description": g.description,
            "logo": g.logo, "cover": g.cover, "banner": g.banner,
            "status": g.status, "featured": g.featured, "popular": g.popular}


@router.get("")
def list_games(db: Db, featured: bool | None = None, search: str = "", page: int = 1, per_page: int = 24):
    q = db.query(models.Game).filter_by(status="active")
    if featured is not None:
        q = q.filter_by(featured=featured)
    if search:
        q = q.filter(models.Game.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.order_by(models.Game.sort_order, models.Game.name).offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [_game_out(g) for g in items], "total": total, "page": page, "per_page": per_page}


@router.get("/categories")
def categories(db: Db):
    cats = db.query(models.GameCategory).filter_by(is_active=True).order_by(models.GameCategory.sort_order).all()
    return {"items": [{"id": c.id, "name": c.name, "slug": c.slug, "icon": c.icon} for c in cats]}


@router.get("/{slug}")
def game_detail(slug: str, db: Db):
    g = db.query(models.Game).filter_by(slug=slug, status="active").first()
    if not g:
        raise HTTPException(status_code=404, detail="game_not_found")
    products = db.query(models.Product).filter_by(game_id=g.id, status="active").order_by(
        models.Product.sort_order).all()
    return {
        "game": _game_out(g),
        "fields": [{"key": f.key, "label": f.label, "type": f.field_type,
                    "required": f.required, "placeholder": f.placeholder} for f in g.fields],
        "products": [{"id": p.id, "name": p.name, "slug": p.slug, "price": str(p.customer_price),
                      "old_price": str(p.old_price), "currency": p.currency, "image": p.image,
                      "popular": p.popular, "stock": p.stock_status} for p in products],
    }
