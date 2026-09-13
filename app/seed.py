"""First-boot seed: admin user + demo catalog (dev only, idempotent)."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.config import settings
from app.models import Game, GameCategory, Product, Supplier, User, UserRole

log = logging.getLogger("vyron.seed")


async def seed_all(db: AsyncSession) -> None:
    await _seed_admin(db)
    if settings.SEED_DEMO_DATA and settings.APP_ENV != "production":
        await _seed_catalog(db)
    await db.commit()


async def _seed_admin(db: AsyncSession) -> None:
    if not settings.ADMIN_EMAIL:
        return
    exists = (await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))).scalars().first()
    if exists:
        return
    db.add(User(
        email=settings.ADMIN_EMAIL, username="admin",
        password_hash=hash_password(settings.ADMIN_PASSWORD),
        full_name="VYRON Admin", role=UserRole.ADMIN, email_verified=True,
    ))
    await db.flush()
    log.info("seeded admin user %s", settings.ADMIN_EMAIL)


async def _seed_catalog(db: AsyncSession) -> None:
    n_games = (await db.execute(select(Game).limit(1))).scalars().first()
    if n_games:
        return
    cat = GameCategory(slug="mobile", name_uz="Mobil o'yinlar", name_en="Mobile games", name_ru="Мобильные игры")
    db.add(cat)
    await db.flush()
    manual = Supplier(code="manual", name="Manual fulfilment", status="ACTIVE")
    db.add(manual)
    await db.flush()

    games = [
        ("pubg-mobile", "PUBG Mobile", [{"key": "player_id", "label": {"uz": "O'yinchi ID", "en": "Player ID", "ru": "ID игрока"}, "required": True}]),
        ("roblox", "Roblox", [{"key": "username", "label": {"uz": "Foydalanuvchi nomi", "en": "Username", "ru": "Имя пользователя"}, "required": True}]),
        ("clash-of-clans", "Clash of Clans", [{"key": "player_tag", "label": {"uz": "O'yinchi tegi", "en": "Player tag", "ru": "Тег игрока"}, "required": True}]),
        ("clash-royale", "Clash Royale", [{"key": "player_tag", "label": {"uz": "O'yinchi tegi", "en": "Player tag", "ru": "Тег игрока"}, "required": True}]),
        ("cs2", "Counter-Strike 2", [{"key": "steam_id", "label": {"uz": "Steam ID", "en": "Steam ID", "ru": "Steam ID"}, "required": True}]),
        ("standoff-2", "Standoff 2", [{"key": "player_id", "label": {"uz": "O'yinchi ID", "en": "Player ID", "ru": "ID игрока"}, "required": True}]),
    ]
    products = [
        ("60 UC", 12000), ("325 UC", 60000), ("660 UC", 120000),
        ("100 Robux", 15000), ("400 Robux", 55000), ("800 Robux", 105000),
    ]
    for i, (slug, title, fields) in enumerate(games):
        g = Game(slug=slug, title=title, category_id=cat.id, fields_schema=fields,
                 supplier_id=manual.id, is_featured=i < 3)
        db.add(g)
        await db.flush()
        for j in range(2):
            name, price = products[(i + j) % len(products)]
            db.add(Product(game_id=g.id, name=f"{title} — {name}", supplier_id=manual.id,
                           supplier_cost=price * 0.8, selling_price=price,
                           currency=settings.DEFAULT_CURRENCY, is_popular=j == 0))
    await db.flush()
    log.info("seeded demo catalog")
