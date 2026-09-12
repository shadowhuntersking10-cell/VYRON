"""Public games & products API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from vyron.api.deps import ok, paginated
from vyron.db.base import get_db
from vyron.db.models import Game, Product
from vyron.enums import GameStatus
from vyron.errors import NotFoundError
from vyron.web.serializers import game_public, product_public

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/games")
def list_games(
    db: DbSession = Depends(get_db),
    featured: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    query = db.query(Game).filter(Game.status == GameStatus.ACTIVE.value)
    if featured is not None:
        query = query.filter(Game.is_featured == featured)
    total = query.count()
    games = query.order_by(Game.sort_order, Game.name).offset((page - 1) * page_size).limit(page_size).all()
    data = [game_public(g) for g in games]
    return paginated(data, total, page, page_size)


@router.get("/games/{slug}")
def get_game(slug: str, db: DbSession = Depends(get_db)):
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
    data = game_public(game)
    data["products"] = [product_public(p) for p in products]
    return ok(data)


@router.get("/products")
def list_products(
    db: DbSession = Depends(get_db),
    game_id: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    query: Optional[str] = Query(None, max_length=80),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    q = db.query(Product).options(joinedload(Product.variants)).filter(Product.active.is_(True))
    if game_id:
        q = q.filter(Product.game_id == game_id)
    if type:
        q = q.filter(Product.type == type.upper())
    if query:
        like = f"%{query.strip()}%"
        q = q.filter(Product.name.like(like) | Product.description.like(like))
    total = q.count()
    products = q.order_by(Product.is_featured.desc(), Product.sort_order, Product.name).offset((page - 1) * page_size).limit(page_size).all()
    data = [product_public(p) for p in products]
    return paginated(data, total, page, page_size)


@router.get("/products/{slug}")
def get_product(slug: str, db: DbSession = Depends(get_db)):
    product = (
        db.query(Product)
        .options(joinedload(Product.variants))
        .filter(Product.slug == slug, Product.active.is_(True))
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found.")
    return ok(product_public(product))
