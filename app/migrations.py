"""Versioned schema migrations + seed data. Runs automatically at startup."""
from __future__ import annotations

from sqlalchemy import select, text

from app.db import Base, get_engine, session_scope
from app.logging_config import get_logger
from app.models import (
    AdminSetting,
    CouponCode,
    FulfillmentType,
    Game,
    Product,
    ProductType,
    ProductVariant,
    Role,
    RoleName,
    Supplier,
)

log = get_logger("vyron.migrations")

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INT NOT NULL PRIMARY KEY,"
        " applied_at DATETIME NOT NULL)",
    ),
]


def run_migrations() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with session_scope() as session:
        # bootstrap the version table first (idempotent)
        for stmt in MIGRATIONS[0][1].split(";"):
            if stmt.strip():
                session.execute(text(stmt))
        for version, sql in MIGRATIONS:
            exists = session.execute(
                text("SELECT COUNT(*) FROM schema_migrations WHERE version = :v"),
                {"v": version},
            ).scalar()
            if not exists:
                for stmt in sql.split(";"):
                    if stmt.strip():
                        session.execute(text(stmt))
                session.execute(
                    text("INSERT INTO schema_migrations (version, applied_at) "
                         "VALUES (:v, CURRENT_TIMESTAMP)"),
                    {"v": version},
                )
        log.info("Migrations applied (schema version %s)", max(v for v, _ in MIGRATIONS))


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
# Desired VYRON catalog structure (per master spec §9). These are GAME
# records only — no prices, no supplier IDs. Products/variants become
# purchasable ONLY after a real supplier (Payerpin) catalog sync maps them.
GAMES_SEED: list[dict] = [
    # slug, name, uz, ru, category, currency_label
    ("pubg-mobile", "PUBG Mobile", "PUBG Mobile", "PUBG Mobile", "mobile", "UC"),
    ("roblox", "Roblox", "Roblox", "Roblox", "mobile", "Robux"),
    ("clash-of-clans", "Clash of Clans", "Clash of Clans", "Clash of Clans", "mobile", "Gems"),
    ("clash-royale", "Clash Royale", "Clash Royale", "Clash Royale", "mobile", "Gems"),
    ("standoff-2", "Standoff 2", "Standoff 2", "Standoff 2", "mobile", "Gold"),
    ("free-fire", "Free Fire", "Free Fire", "Free Fire", "mobile", "Diamonds"),
    ("free-fire-max", "Free Fire MAX", "Free Fire MAX", "Free Fire MAX", "mobile", "Diamonds"),
    ("mobile-legends", "Mobile Legends: Bang Bang", "Mobile Legends: Bang Bang",
     "Mobile Legends: Bang Bang", "mobile", "Diamonds"),
    ("honor-of-kings", "Honor of Kings", "Honor of Kings", "Honor of Kings", "mobile", "Tokens"),
    ("league-of-legends", "League of Legends", "League of Legends", "League of Legends",
     "pc", "RP"),
    ("valorant", "VALORANT", "VALORANT", "VALORANT", "pc", "VP"),
    ("counter-strike-2", "Counter-Strike 2", "Counter-Strike 2", "Counter-Strike 2", "pc", "Credits"),
    ("dota-2", "Dota 2", "Dota 2", "Dota 2", "pc", "Shards"),
    ("ea-sports-fc", "EA SPORTS FC", "EA SPORTS FC", "EA SPORTS FC", "console", "FC Points"),
    ("genshin-impact", "Genshin Impact", "Genshin Impact", "Genshin Impact", "mobile", "Primogems"),
    ("honkai-star-rail", "Honkai: Star Rail", "Honkai: Star Rail", "Honkai: Star Rail", "mobile",
     "Oneiric Shards"),
    ("zenless-zone-zero", "Zenless Zone Zero", "Zenless Zone Zero", "Zenless Zone Zero", "mobile",
     "Polychrome"),
    ("wuthering-waves", "Wuthering Waves", "Wuthering Waves", "Wuthering Waves", "mobile",
     "Lunite"),
    ("cod-mobile", "Call of Duty: Mobile", "Call of Duty: Mobile", "Call of Duty: Mobile",
     "mobile", "CP"),
    ("cod-warzone", "Call of Duty: Warzone", "Call of Duty: Warzone", "Call of Duty: Warzone",
     "pc", "CP"),
    ("arena-breakout", "Arena Breakout", "Arena Breakout", "Arena Breakout", "mobile", "Bonds"),
    ("pubg-battlegrounds", "PUBG: BATTLEGROUNDS", "PUBG: BATTLEGROUNDS", "PUBG: BATTLEGROUNDS",
     "pc", "G-Coins"),
    ("minecraft", "Minecraft", "Minecraft", "Minecraft", "pc", "Minecoins"),
    ("tlauncher", "TLauncher Products", "TLauncher mahsulotlari", "Продукты TLauncher", "pc",
     "License"),
    ("brawl-stars", "Brawl Stars", "Brawl Stars", "Brawl Stars", "mobile", "Gems"),
    ("pokemon-go", "Pokémon GO", "Pokémon GO", "Pokémon GO", "mobile", "PokéCoins"),
    ("efootball", "eFootball", "eFootball", "eFootball", "console", "Coins"),
    ("asphalt", "Asphalt", "Asphalt", "Asphalt", "mobile", "Tokens"),
    ("xbox", "Xbox", "Xbox", "Xbox", "gift-cards", "USD"),
    ("playstation", "PlayStation", "PlayStation", "PlayStation", "gift-cards", "USD"),
    ("nintendo", "Nintendo", "Nintendo", "Nintendo", "gift-cards", "USD"),
    ("google-play", "Google Play", "Google Play", "Google Play", "gift-cards", "USD"),
    ("apple-gift-card", "Apple Gift Card", "Apple Gift Card", "Apple Gift Card", "gift-cards",
     "USD"),
    ("discord", "Discord", "Discord", "Discord", "digital", "Nitro"),
    ("twitch", "Twitch", "Twitch", "Twitch", "digital", "Bits"),
    ("battlenet", "Battle.net", "Battle.net", "Battle.net", "gift-cards", "USD"),
    ("steam", "Steam", "Steam", "Steam", "gift-cards", "USD"),
    ("telegram-stars", "Telegram Stars", "Telegram Stars", "Telegram Stars", "digital", "Stars"),
    ("gift-cards", "Gift Cards", "Sovg'a kartalari", "Подарочные карты", "gift-cards", "USD"),
    ("other-products", "Other Products", "Boshqa mahsulotlar", "Другие продукты", "digital", ""),
]

FEATURED_SLUGS = {
    "pubg-mobile", "free-fire", "mobile-legends", "roblox",
    "standoff-2", "clash-of-clans", "genshin-impact", "steam",
}

CURRENCY_STYLES: dict[str, dict] = {
    # currency_label -> gradient + glyph used for generated currency art
    "UC": {"a": "#1D4ED8", "b": "#60A5FA", "g": "UC"},
    "Robux": {"a": "#E11D48", "b": "#FB7185", "g": "R$"},
    "Gems": {"a": "#7C3AED", "b": "#C084FC", "g": "◆"},
    "Gold": {"a": "#B45309", "b": "#FBBF24", "g": "Au"},
    "Diamonds": {"a": "#0E7490", "b": "#67E8F9", "g": "◆"},
    "Tokens": {"a": "#0F766E", "b": "#5EEAD4", "g": "✦"},
    "RP": {"a": "#B91C1C", "b": "#F87171", "g": "RP"},
    "VP": {"a": "#9F1239", "b": "#FB7185", "g": "VP"},
    "Credits": {"a": "#334155", "b": "#94A3B8", "g": "CR"},
    "Shards": {"a": "#3730A3", "b": "#818CF8", "g": "◈"},
    "FC Points": {"a": "#065F46", "b": "#34D399", "g": "FC"},
    "Primogems": {"a": "#4338CA", "b": "#A5B4FC", "g": "✦"},
    "Oneiric Shards": {"a": "#5B21B6", "b": "#C4B5FD", "g": "◇"},
    "Polychrome": {"a": "#9A3412", "b": "#FDBA74", "g": "⬡"},
    "Lunite": {"a": "#1E3A8A", "b": "#93C5FD", "g": "☾"},
    "CP": {"a": "#166534", "b": "#86EFAC", "g": "CP"},
    "Bonds": {"a": "#78350F", "b": "#FCD34D", "g": "▣"},
    "G-Coins": {"a": "#0F172A", "b": "#64748B", "g": "G"},
    "Minecoins": {"a": "#166534", "b": "#4ADE80", "g": "⛏"},
    "License": {"a": "#0C4A6E", "b": "#38BDF8", "g": "TL"},
    "PokéCoins": {"a": "#1D4ED8", "b": "#FBBF24", "g": "₽"},  # coin glyph replaced below
    "Coins": {"a": "#A16207", "b": "#FDE047", "g": "◉"},
    "USD": {"a": "#064E3B", "b": "#6EE7B7", "g": "$"},
    "Nitro": {"a": "#4C1D95", "b": "#A78BFA", "g": "N"},
    "Bits": {"a": "#3730A3", "b": "#8B5CF6", "g": "♦"},
    "Stars": {"a": "#0369A1", "b": "#7DD3FC", "g": "★"},
    "": {"a": "#0B2447", "b": "#4DA8DA", "g": "V"},
}


def _currency_art(currency_label: str) -> str:
    """SVG data-URI showing ONLY the relevant game currency (soft UI style)."""
    style = CURRENCY_STYLES.get(currency_label, CURRENCY_STYLES[""])
    glyph = currency_label if currency_label and currency_label != "PokéCoins" else style["g"]
    if currency_label == "PokéCoins":
        glyph = "◉"
    glyph = glyph if len(glyph) <= 3 else glyph[:2]
    label = currency_label or "Digital"
    return (
        "data:image/svg+xml;utf8,"
        + (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='480' height='320' viewBox='0 0 480 320'>"
            f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            f"<stop offset='0' stop-color='{style['a']}'/><stop offset='1' stop-color='{style['b']}'/>"
            f"</linearGradient>"
            f"<radialGradient id='s' cx='0.5' cy='0.35' r='0.7'>"
            f"<stop offset='0' stop-color='#ffffff' stop-opacity='0.35'/>"
            f"<stop offset='1' stop-color='#ffffff' stop-opacity='0'/>"
            f"</radialGradient></defs>"
            f"<rect width='480' height='320' rx='36' fill='url(#g)'/>"
            f"<rect width='480' height='320' rx='36' fill='url(#s)'/>"
            f"<circle cx='240' cy='150' r='78' fill='#ffffff' fill-opacity='0.18'/>"
            f"<circle cx='240' cy='150' r='62' fill='#ffffff' fill-opacity='0.25'/>"
            f"<text x='240' y='172' font-family='Segoe UI, Arial, sans-serif' font-size='58' "
            f"font-weight='800' fill='#ffffff' text-anchor='middle'>{glyph}</text>"
            f"<text x='240' y='272' font-family='Segoe UI, Arial, sans-serif' font-size='28' "
            f"font-weight='700' fill='#ffffff' fill-opacity='0.92' text-anchor='middle'>{label}</text>"
            f"</svg>"
        ).replace("#", "%23").replace('"', "'")
    )


def seed_database() -> None:
    with session_scope() as session:
        # roles
        for role_name, label in (
            (RoleName.ADMIN, "Administrator"),
            (RoleName.SUPPORT, "Support"),
            (RoleName.CUSTOMER, "Customer"),
        ):
            if not session.execute(
                select(Role).where(Role.name == role_name)
            ).scalar_one_or_none():
                session.add(Role(name=role_name, label=label))

        # supplier: payerpin
        if not session.execute(
            select(Supplier).where(Supplier.code == "payerpin")
        ).scalar_one_or_none():
            session.add(
                Supplier(
                    code="payerpin",
                    name="Payerpin",
                    config={"base_url": "https://api.payerpin.uz", "api_version": "v2"},
                )
            )

        # default pricing settings (public schema, no secrets)
        if not session.execute(
            select(AdminSetting).where(AdminSetting.key == "pricing")
        ).scalar_one_or_none():
            session.add(
                AdminSetting(
                    key="pricing",
                    value={
                        "margin_percent": 10,
                        "margin_fixed": 0,
                        "payment_fee_percent": 0,
                        "payment_fee_fixed": 0,
                        "min_margin_percent": 0,
                        "allow_below_min_margin": False,
                    },
                )
            )
        if not session.execute(
            select(AdminSetting).where(AdminSetting.key == "general")
        ).scalar_one_or_none():
            session.add(
                AdminSetting(
                    key="general",
                    value={
                        "support_link": "https://t.me/vyron_support",
                        "announcement_uz": "",
                        "announcement_en": "",
                        "announcement_ru": "",
                    },
                )
            )

        # games catalog structure (NOT purchasable until supplier sync)
        existing = {
            g.slug for g in session.execute(select(Game)).scalars().all()
        }
        for i, (slug, name, name_uz, name_ru, category, cur) in enumerate(GAMES_SEED):
            if slug in existing:
                continue
            art = _currency_art(cur)
            game = Game(
                slug=slug,
                name=name,
                name_uz=name_uz,
                name_ru=name_ru,
                category=category,
                currency_label=cur,
                icon_url=art,
                logo_url=art,
                banner_url=art,
                sort_order=i,
                featured=slug in FEATURED_SLUGS,
                active=True,
            )
            session.add(game)
            session.flush()
            # Inactive product shell: NOT purchasable, NOT priced — awaits
            # real Payerpin catalog sync (never invent supplier IDs / prices).
            product = Product(
                game_id=game.id,
                slug=f"{slug}-topup",
                name=f"{name} Top-up" if category != "gift-cards" else f"{name} Gift Card",
                product_type=(
                    ProductType.GIFT_CARD if category == "gift-cards"
                    else ProductType.TOPUP if category in ("mobile", "pc", "console")
                    else ProductType.DIGITAL
                ),
                fulfillment_type=FulfillmentType.AUTO,
                image_url=art,
                required_fields={"fields": []},
                active=False,
                visibility=True,
            )
            session.add(product)

        # demo coupon (public marketing seed, harmless)
        if not session.execute(
            select(CouponCode).where(CouponCode.code == "WELCOME5")
        ).scalar_one_or_none():
            session.add(
                CouponCode(
                    code="WELCOME5",
                    coupon_type="PERCENT",
                    value=5,
                    min_order_amount=0,
                    per_user_limit=1,
                    max_uses=None,
                    expires_at=None,
                )
            )
    log.info("Seed data ready (games catalog structure, roles, supplier, settings)")
