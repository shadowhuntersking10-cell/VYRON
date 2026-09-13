"""First-boot seed: admin user + full demo catalog (dev only, idempotent).

Honesty: seed products use the MANUAL supplier, so paid orders route to
MANUAL_REVIEW until a real supplier API is configured. No fake payments,
no fake completions - ever.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.config import settings
from app.models import (
    Coupon, DonationPreset, DonationProfile, Game, GameCategory, GameField,
    ListingImage, MarketplaceCategory, MarketplaceListing,
    Product, Promotion, Seller, SellerBalance, Setting, Supplier, User, UserRole,
)

log = logging.getLogger("vyron.seed")
CUR = settings.DEFAULT_CURRENCY


def L(uz: str, en: str, ru: str) -> dict:
    return {"uz": uz, "en": en, "ru": ru}


def F(key: str, uz: str, en: str, ru: str, required: bool = True) -> dict:
    return {"key": key, "label": L(uz, en, ru), "required": required}


PLAYER_ID = [F("player_id", "O'yinchi ID", "Player ID", "ID игрока"),
             F("region", "Region (ixtiyoriy)", "Region (optional)", "Регион (необязательно)", False)]
USERNAME = [F("username", "Foydalanuvchi nomi", "Username", "Имя пользователя")]
PLAYER_TAG = [F("player_tag", "O'yinchi tegi", "Player tag", "Тег игрока")]
REGION_ONLY = [F("region", "Region", "Region", "Регион")]
RIOT = [F("riot_id", "Riot ID (Name#TAG)", "Riot ID (Name#TAG)", "Riot ID (Name#TAG)")]
MLBB = [F("user_id", "O'yin ID", "Game ID", "ID игры"),
        F("server", "Server ID", "Server ID", "ID сервера")]


# slug, title, category, fields, featured, description, products[(name, cost, price, popular)]
GAMES: list[tuple] = [
    ("pubg-mobile", "PUBG Mobile", "mobile", PLAYER_ID, True,
     "Unknown Cash (UC) for PUBG Mobile - instant top-up to your Player ID.",
     [("60 UC", 11500, 14000, False), ("325 UC", 57000, 69000, True),
      ("660 UC", 114000, 139000, False), ("1800 UC", 285000, 349000, False),
      ("3850 UC", 560000, 689000, False), ("8100 UC", 1130000, 1390000, False)]),
    ("roblox", "Roblox", "mobile", USERNAME, True,
     "Robux and Premium for your Roblox account.",
     [("400 Robux", 54000, 65000, False), ("800 Robux", 105000, 129000, True),
      ("1,700 Robux", 210000, 259000, False), ("4,500 Robux", 530000, 649000, False),
      ("10,000 Robux", 1050000, 1290000, False), ("Premium 450 / month", 54000, 65000, False)]),
    ("clash-of-clans", "Clash of Clans", "mobile", PLAYER_TAG, False,
     "Gold Pass and Gems for Clash of Clans.",
     [("Gold Pass", 75000, 89000, True), ("Gems 80", 12000, 15000, False),
      ("Gems 500", 57000, 69000, False), ("Gems 1,200", 114000, 139000, False),
      ("Gems 2,500", 225000, 279000, False), ("Gems 6,500", 530000, 649000, False)]),
    ("clash-royale", "Clash Royale", "mobile", PLAYER_TAG, False,
     "Pass Royale and Gems for Clash Royale.",
     [("Pass Royale", 75000, 89000, True), ("Gems 80", 12000, 15000, False),
      ("Gems 500", 57000, 69000, False), ("Gems 1,200", 114000, 139000, False),
      ("Gems 2,500", 225000, 279000, False)]),
    ("counter-strike-2", "Counter-Strike 2", "pc", [F("steam_id", "Steam ID / profile URL", "Steam ID / profile URL", "Steam ID / ссылка")], False,
     "Steam Wallet codes and Prime Status for CS2 players.",
     [("Steam Wallet $5", 65000, 79000, False), ("Steam Wallet $10", 130000, 159000, True),
      ("Steam Wallet $20", 260000, 319000, False), ("Steam Wallet $50", 650000, 790000, False),
      ("Prime Status", 190000, 229000, False)]),
    ("standoff-2", "Standoff 2", "mobile", PLAYER_ID, True,
     "Gold, cases and bundles for Standoff 2.",
     [("100 Gold", 12000, 15000, False), ("500 Gold", 54000, 65000, True),
      ("1,000 Gold", 105000, 129000, False), ("3,000 Gold", 300000, 369000, False),
      ("Case Bundle x5", 45000, 55000, False)]),
    ("free-fire", "Free Fire", "mobile", PLAYER_ID, False,
     "Diamonds and passes for Free Fire.",
     [("100 Diamonds", 11000, 13000, False), ("310 Diamonds", 33000, 39000, True),
      ("520 Diamonds", 55000, 65000, False), ("1,060 Diamonds", 110000, 129000, False),
      ("2,180 Diamonds", 215000, 259000, False), ("Weekly Pass", 22000, 26000, False),
      ("Monthly Pass", 110000, 129000, False)]),
    ("mobile-legends", "Mobile Legends", "mobile", MLBB, False,
     "Diamonds for Mobile Legends: Bang Bang.",
     [("86 Diamonds", 14000, 17000, False), ("172 Diamonds", 28000, 34000, False),
      ("257 Diamonds", 42000, 50000, True), ("344 Diamonds", 56000, 67000, False),
      ("706 Diamonds", 112000, 135000, False), ("Twilight Pass", 110000, 129000, False)]),
    ("brawl-stars", "Brawl Stars", "mobile", PLAYER_TAG, False,
     "Gems and Brawl Pass for Brawl Stars.",
     [("80 Gems", 14000, 17000, False), ("170 Gems", 28000, 34000, False),
      ("360 Gems", 55000, 65000, True), ("950 Gems", 140000, 169000, False),
      ("2,000 Gems", 275000, 329000, False), ("Brawl Pass", 83000, 99000, False)]),
    ("valorant", "Valorant", "pc", RIOT, False,
     "Valorant Points (VP) for your Riot account.",
     [("475 VP", 55000, 65000, False), ("1,000 VP", 110000, 129000, True),
      ("2,050 VP", 215000, 259000, False), ("3,650 VP", 380000, 459000, False),
      ("5,350 VP", 540000, 649000, False)]),
    ("fortnite", "Fortnite", "pc", [F("epic_username", "Epic username", "Epic username", "Epic-логин")], False,
     "V-Bucks and Fortnite Crew.",
     [("1,000 V-Bucks", 110000, 129000, True), ("2,800 V-Bucks", 290000, 349000, False),
      ("5,000 V-Bucks", 480000, 579000, False), ("Crew - 1 month", 140000, 169000, False)]),
    ("ea-sports-fc", "EA Sports FC", "console", [F("platform", "Platforma (PS/Xbox/PC)", "Platform (PS/Xbox/PC)", "Платформа (PS/Xbox/PC)")], False,
     "FC Points for Ultimate Team.",
     [("1,050 FC Points", 130000, 159000, False), ("2,800 FC Points", 330000, 399000, True),
      ("5,900 FC Points", 660000, 790000, False), ("12,000 FC Points", 1300000, 1590000, False)]),
    ("league-of-legends", "League of Legends", "pc", RIOT, False,
     "Riot Points (RP) for League of Legends.",
     [("650 RP", 65000, 79000, False), ("1,380 RP", 130000, 159000, True),
      ("2,800 RP", 260000, 319000, False), ("5,000 RP", 460000, 559000, False)]),
    ("minecraft", "Minecraft", "pc", USERNAME, False,
     "Minecraft Java & Bedrock, Minecoins and Realms.",
     [("Java & Bedrock Edition", 350000, 429000, True), ("Minecoins 1,720", 110000, 129000, False),
      ("Minecoins 3,500", 200000, 249000, False), ("Realms - 1 month", 95000, 115000, False)]),
    ("steam", "Steam", "gift-cards", REGION_ONLY, True,
     "Steam Wallet gift cards (global & region codes).",
     [("Wallet $5", 68000, 79000, False), ("Wallet $10", 135000, 159000, True),
      ("Wallet $20", 270000, 315000, False), ("Wallet $50", 670000, 790000, False),
      ("Wallet $100", 1330000, 1570000, False)]),
    ("playstation", "PlayStation", "gift-cards", REGION_ONLY, False,
     "PSN cards and PS Plus subscriptions.",
     [("PSN $10", 135000, 159000, False), ("PSN $25", 330000, 390000, True),
      ("PSN $50", 660000, 790000, False), ("PS Plus Essential - 1 mo", 110000, 129000, False),
      ("PS Plus Essential - 12 mo", 700000, 840000, False)]),
    ("xbox", "Xbox", "gift-cards", REGION_ONLY, False,
     "Xbox gift cards and Game Pass Ultimate.",
     [("Xbox $10", 135000, 159000, False), ("Xbox $25", 330000, 390000, False),
      ("Xbox $50", 660000, 790000, False), ("Game Pass Ultimate - 1 mo", 150000, 179000, True),
      ("Game Pass Ultimate - 3 mo", 430000, 519000, False)]),
    ("apple", "Apple", "gift-cards", REGION_ONLY, False,
     "Apple Gift Cards for App Store & iTunes.",
     [("$5", 68000, 79000, False), ("$10", 135000, 159000, True),
      ("$25", 330000, 390000, False), ("$50", 660000, 790000, False)]),
    ("google-play", "Google Play", "gift-cards", REGION_ONLY, False,
     "Google Play gift cards.",
     [("$5", 68000, 79000, False), ("$10", 135000, 159000, True),
      ("$25", 330000, 390000, False), ("$50", 660000, 790000, False)]),
]

CATEGORIES = [
    ("mobile", "Mobil o'yinlar", "Mobile games", "Мобильные игры", 10),
    ("pc", "Kompyuter o'yinlari", "PC games", "ПК-игры", 20),
    ("console", "Konsol o'yinlari", "Console games", "Консольные игры", 30),
    ("gift-cards", "Gift kartalar", "Gift cards", "Гифт-карты", 40),
]


async def seed_all(db: AsyncSession) -> None:
    await _seed_admin(db)
    if settings.SEED_DEMO_DATA and settings.APP_ENV != "production":
        await _seed_catalog(db)
        await _seed_extras(db)
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
    if (await db.execute(select(Game).limit(1))).scalars().first():
        return
    cat_ids: dict[str, int] = {}
    for slug, uz, en, ru, order in CATEGORIES:
        c = GameCategory(slug=slug, name_uz=uz, name_en=en, name_ru=ru, sort_order=order)
        db.add(c)
        await db.flush()
        cat_ids[slug] = c.id

    manual = Supplier(code="manual", name="Manual fulfilment", status="ACTIVE")
    db.add(manual)
    generic = Supplier(code="generic", name="Generic top-up API", status="NOT_CONFIGURED")
    db.add(generic)
    await db.flush()

    accents = {
        "pubg-mobile": "#7a2d12", "roblox": "#8f1d1d", "clash-of-clans": "#92400e",
        "clash-royale": "#1e3a8a", "counter-strike-2": "#7c2d12", "standoff-2": "#334155",
        "free-fire": "#991b1b", "mobile-legends": "#1e40af", "brawl-stars": "#a21caf",
        "valorant": "#881337", "fortnite": "#4c1d95", "ea-sports-fc": "#065f46",
        "league-of-legends": "#713f12", "minecraft": "#14532d", "steam": "#0b1f3a",
        "playstation": "#1e3a8a", "xbox": "#14532d", "apple": "#111827",
        "google-play": "#0e7490",
    }
    n_products = 0
    for i, (slug, title, cat, fields, featured, desc, products) in enumerate(GAMES):
        logo = f"/static/images/games/{slug}.svg"
        g = Game(slug=slug, title=title, description=desc, category_id=cat_ids[cat],
                 logo_url=logo, cover_url=f"/static/images/covers/{slug}.svg",
                 accent_color=accents.get(slug, "#0B1F3A"),
                 fields_schema=fields, supplier_id=manual.id,
                 is_featured=featured, is_demo=True, sort_order=i)
        db.add(g)
        await db.flush()
        for order, f in enumerate(fields):
            label = f.get("label", {})
            db.add(GameField(game_id=g.id, key=f.get("key", ""), label_uz=label.get("uz", ""),
                             label_en=label.get("en", ""), label_ru=label.get("ru", ""),
                             required=bool(f.get("required", True)), sort_order=order))
        for name, cost, price, popular in products:
            db.add(Product(game_id=g.id, name=f"{title} - {name}", image_url=logo,
                           supplier_id=manual.id, supplier_cost=cost, selling_price=price,
                           currency=CUR, is_popular=popular, is_demo=True,
                           sort_order=n_products))
            n_products += 1
    await db.flush()
    log.info("seeded %d games, %d products", len(GAMES), n_products)


async def _seed_extras(db: AsyncSession) -> None:
    # Settings: donation presets + marketplace categories + fees
    presets = {
        "UZS": [10000, 25000, 50000, 100000, 250000, 500000],
        "USD": [1, 2, 5, 10, 20, 50, 100],
        "RUB": [100, 300, 500, 1000, 2500, 5000],
    }
    defaults = {
        "donation_presets": json.dumps(presets),
        "marketplace_categories": "accounts,items,currency,boosting,giftcards,other",
        "payment_fee_percent": "1.5",
        "promotion_price": "50000",
        "seller_premium_price": "99000",
    }
    for key, value in defaults.items():
        if not await db.get(Setting, key):
            db.add(Setting(key=key, value=value))

    # Marketplace categories (structured, with commission overrides)
    mkt_cats = [
        ("accounts", "Hisoblar", "Accounts", "Аккаунты", None),
        ("items", "Buyumlar", "Items", "Предметы", None),
        ("currency", "Valyuta", "Currency", "Валюта", None),
        ("boosting", "Boosting", "Boosting", "Буст", "15.0"),
        ("giftcards", "Gift kartalar", "Gift cards", "Гифт-карты", None),
        ("other", "Boshqa", "Other", "Другое", None),
    ]
    for order, (slug, uz, en, ru, comm) in enumerate(mkt_cats):
        if not (await db.execute(select(MarketplaceCategory).where(MarketplaceCategory.slug == slug))).scalars().first():
            from decimal import Decimal as _D
            db.add(MarketplaceCategory(slug=slug, name_uz=uz, name_en=en, name_ru=ru,
                                       commission_percent=_D(comm) if comm else None,
                                       sort_order=order))

    # Donation presets (structured; settings JSON remains as fallback)
    from decimal import Decimal as _D2
    for currency, amounts in (("UZS", [10000, 25000, 50000, 100000, 250000, 500000, 1000000]),
                              ("USD", [1, 2, 5, 10, 20, 50, 100])):
        for order, amount in enumerate(amounts):
            exists = (await db.execute(select(DonationPreset).where(
                DonationPreset.currency == currency, DonationPreset.amount == _D2(amount)))).scalars().first()
            if not exists:
                db.add(DonationPreset(currency=currency, amount=_D2(amount), sort_order=order))

    # Coupon + promotions
    if not (await db.execute(select(Coupon).where(Coupon.code == "WELCOME10"))).scalars().first():
        from decimal import Decimal
        db.add(Coupon(code="WELCOME10", kind="percent", value=Decimal(10),
                      min_order=Decimal(20000), max_uses=1000, per_user_limit=1))
    if not (await db.execute(select(Promotion).limit(1))).scalars().first():
        db.add(Promotion(slug="welcome10", title="WELCOME10 - 10% off your first top-up",
                         description="Use coupon WELCOME10 at checkout. Min order 20,000 UZS."))
        db.add(Promotion(slug="weekend-uc", title="Weekend UC deals",
                         description="Best prices on PUBG Mobile UC every weekend."))

    # Demo donation profiles
    if not (await db.execute(select(User).where(User.email == "demo.creator@vyron.local"))).scalars().first():
        creator = User(email="demo.creator@vyron.local", username="demo_creator",
                       password_hash=hash_password("Demo12345!"), full_name="Demo Creator")
        db.add(creator)
        await db.flush()
        db.add(DonationProfile(user_id=creator.id, username="demo_creator", display_name="Demo Creator",
                               cover_url="/static/images/covers/pubg-mobile.svg",
                               bio="Demo donation profile (seed data). I stream PUBG Mobile every evening!",
                               goal_title="New microphone", goal_amount=1500000, currency=CUR))
        streamer = User(email="demo.streamer@vyron.local", username="demo_streamer",
                        password_hash=hash_password("Demo12345!"), full_name="Demo Streamer")
        db.add(streamer)
        await db.flush()
        db.add(DonationProfile(user_id=streamer.id, username="demo_streamer", display_name="Demo Streamer",
                               cover_url="/static/images/covers/roblox.svg",
                               bio="Demo donation profile (seed data). Variety streams UZ/EN/RU.",
                               goal_title="PC upgrade fund", goal_amount=8000000, currency=CUR))

    # Demo seller + listings
    if not (await db.execute(select(User).where(User.email == "demo.seller@vyron.local"))).scalars().first():
        su = User(email="demo.seller@vyron.local", username="demo_seller",
                  password_hash=hash_password("Demo12345!"), full_name="Demo Seller",
                  role=UserRole.SELLER)
        db.add(su)
        await db.flush()
        seller = Seller(user_id=su.id, shop_name="Demo Store", is_verified=True,
                        description="Demo seller (seed data). Fast delivery, trusted trader.")
        db.add(seller)
        await db.flush()
        db.add(SellerBalance(seller_id=seller.id, currency=CUR))
        demo_listings = [
            ("PUBG Mobile Conqueror account", "Demo listing (seed data). Full access, EU region.", 450000, "accounts"),
            ("10,000 Mobile Legends diamonds piloting", "Demo listing (seed data). Safe boosting by top players.", 120000, "boosting"),
            ("Steam $20 gift card", "Demo listing (seed data). Global code, instant delivery.", 315000, "giftcards"),
        ]
        categories = {c.slug: c.id for c in
                      (await db.execute(select(MarketplaceCategory))).scalars().all()}
        art = {"accounts": "/static/images/games/pubg-mobile.svg",
               "boosting": "/static/images/games/mobile-legends.svg",
               "giftcards": "/static/images/games/steam.svg"}
        for title, desc, price, cat in demo_listings:
            listing = MarketplaceListing(seller_id=seller.id, title=title, description=desc,
                                         price=price, currency=CUR, category=cat,
                                         category_id=categories.get(cat), status="active")
            db.add(listing)
            await db.flush()
            if art.get(cat):
                db.add(ListingImage(listing_id=listing.id, url=art[cat],
                                    alt_text=title, sort_order=0))
    await db.flush()
    log.info("seeded extras (presets, coupon, promotions, demo donations, demo seller)")
