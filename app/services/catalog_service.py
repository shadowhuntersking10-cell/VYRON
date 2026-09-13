"""Games / products read + admin write helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Game, GameCategory, Product, ProductVariant


async def list_games(db: AsyncSession, *, active_only: bool = True, featured_first: bool = True) -> list[Game]:
    stmt = select(Game).order_by(Game.sort_order, Game.id)
    if active_only:
        stmt = stmt.where(Game.is_active.is_(True))
    games = list((await db.execute(stmt)).scalars().all())
    if featured_first:
        games.sort(key=lambda g: (not g.is_featured, g.sort_order, g.id))
    return games


async def get_game_by_slug(db: AsyncSession, slug: str) -> Game | None:
    return (await db.execute(select(Game).where(Game.slug == slug))).scalars().first()


async def list_products_for_game(db: AsyncSession, game_id: int, *, active_only: bool = True) -> list[Product]:
    stmt = select(Product).where(Product.game_id == game_id).order_by(Product.sort_order, Product.id)
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_product(db: AsyncSession, product_id: int) -> Product | None:
    return await db.get(Product, product_id)


async def get_variant(db: AsyncSession, variant_id: int) -> ProductVariant | None:
    return await db.get(ProductVariant, variant_id)


async def validate_customer_fields(game: Game, fields: dict) -> dict[str, str]:
    """Validate checkout player fields against the game's fields_schema."""
    schema = game.fields_schema or []
    cleaned: dict[str, str] = {}
    errors: list[str] = []
    for item in schema:
        key = item.get("key", "")
        required = bool(item.get("required", True))
        value = str((fields or {}).get(key, "")).strip()
        if required and not value:
            errors.append(key)
        elif value:
            cleaned[key] = value[:255]
    if errors:
        raise ValueError(f"missing_fields:{','.join(errors)}")
    return cleaned


async def categories(db: AsyncSession) -> list[GameCategory]:
    stmt = select(GameCategory).where(GameCategory.is_active.is_(True)).order_by(GameCategory.sort_order)
    return list((await db.execute(stmt)).scalars().all())
