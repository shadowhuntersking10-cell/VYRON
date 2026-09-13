from __future__ import annotations
import logging
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import (
    Game, GameCategory, GameField, Product, Supplier, Role,
    DonationPreset, DonationProfile, User, MarketplaceCategory,
    Promotion, Setting
)
from app.utils.security import hash_password
from app.utils.helpers import slugify

logger = logging.getLogger(__name__)

GAMES_DATA = [
    {
        "name": "PUBG Mobile",
        "slug": "pubg-mobile",
        "short_description": "Battle royale shooter - UC top-ups",
        "description": "PUBG Mobile is the ultimate battle royale experience on mobile. Get UC to unlock Royale Pass, crates, skins and more.",
        "category": "Battle Royale",
        "logo_url": "/static/images/games/pubg-logo.png",
        "cover_url": "/static/images/games/pubg-cover.jpg",
        "banner_url": "/static/images/games/pubg-banner.jpg",
        "featured": True,
        "popular": True,
        "fields": [
            {"field_key": "player_id", "label": "Player ID", "placeholder": "Enter your PUBG Player ID", "required": True},
            {"field_key": "region", "label": "Region", "placeholder": "Select region", "field_type": "select", "required": False}
        ],
        "products": [
            {"name": "60 UC", "price": 15000, "cost": 12000},
            {"name": "325 UC", "price": 75000, "cost": 60000},
            {"name": "660 UC", "price": 145000, "cost": 120000},
            {"name": "1800 UC", "price": 380000, "cost": 320000},
            {"name": "3850 UC", "price": 750000, "cost": 650000},
            {"name": "8100 UC", "price": 1450000, "cost": 1250000},
        ]
    },
    {
        "name": "Roblox",
        "slug": "roblox",
        "short_description": "Create and play - Robux top-ups",
        "description": "Roblox is a global platform for creation and imagination. Get Robux to buy avatar items, game passes and more.",
        "category": "Sandbox",
        "logo_url": "/static/images/games/roblox-logo.png",
        "cover_url": "/static/images/games/roblox-cover.jpg",
        "banner_url": "/static/images/games/roblox-banner.jpg",
        "featured": True,
        "popular": True,
        "fields": [
            {"field_key": "username", "label": "Roblox Username", "placeholder": "Enter Roblox username", "required": True}
        ],
        "products": [
            {"name": "400 Robux", "price": 65000, "cost": 50000},
            {"name": "800 Robux", "price": 125000, "cost": 100000},
            {"name": "1700 Robux", "price": 250000, "cost": 210000},
            {"name": "4500 Robux", "price": 620000, "cost": 530000},
            {"name": "10000 Robux", "price": 1250000, "cost": 1050000},
        ]
    },
    {
        "name": "Clash of Clans",
        "slug": "clash-of-clans",
        "short_description": "Build your village - Gems & Gold Pass",
        "description": "Lead your clan to victory! Clash of Clans gems for builders, resources and Gold Pass.",
        "category": "Strategy",
        "logo_url": "/static/images/games/coc-logo.png",
        "cover_url": "/static/images/games/coc-cover.jpg",
        "banner_url": "/static/images/games/coc-banner.jpg",
        "featured": True,
        "popular": True,
        "fields": [
            {"field_key": "player_tag", "label": "Player Tag", "placeholder": "#XXXX", "required": True}
        ],
        "products": [
            {"name": "80 Gems", "price": 18000, "cost": 14000},
            {"name": "500 Gems", "price": 95000, "cost": 75000},
            {"name": "1200 Gems", "price": 210000, "cost": 175000},
            {"name": "2500 Gems", "price": 420000, "cost": 350000},
            {"name": "6500 Gems", "price": 950000, "cost": 800000},
            {"name": "Gold Pass", "price": 85000, "cost": 65000},
        ]
    },
    {
        "name": "Clash Royale",
        "slug": "clash-royale",
        "short_description": "Real-time battles - Gems",
        "description": "Clash Royale - fast-paced battles with your favorite Clash characters. Gems for chests and Pass Royale.",
        "category": "Strategy",
        "logo_url": "/static/images/games/clash-royale-logo.png",
        "cover_url": "/static/images/games/clash-royale-cover.jpg",
        "banner_url": "/static/images/games/clash-royale-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "player_tag", "label": "Player Tag", "placeholder": "#XXXX", "required": True}
        ],
        "products": [
            {"name": "80 Gems", "price": 18000, "cost": 14000},
            {"name": "500 Gems", "price": 95000, "cost": 75000},
            {"name": "1200 Gems", "price": 210000, "cost": 175000},
            {"name": "2500 Gems", "price": 420000, "cost": 350000},
            {"name": "6500 Gems", "price": 950000, "cost": 800000},
        ]
    },
    {
        "name": "Counter-Strike 2",
        "slug": "counter-strike-2",
        "short_description": "FPS legend - Skins & Prime",
        "description": "Counter-Strike 2 - the legendary FPS. Prime status, cases and more.",
        "category": "FPS",
        "logo_url": "/static/images/games/cs2-logo.png",
        "cover_url": "/static/images/games/cs2-cover.jpg",
        "banner_url": "/static/images/games/cs2-banner.jpg",
        "featured": True,
        "popular": True,
        "fields": [
            {"field_key": "steam_id", "label": "Steam ID / Trade URL", "placeholder": "Enter Steam ID", "required": True}
        ],
        "products": [
            {"name": "CS2 Prime Status", "price": 180000, "cost": 150000},
            {"name": "Recoil Case x5", "price": 45000, "cost": 35000},
            {"name": "Dreams & Nightmares Case x10", "price": 85000, "cost": 70000},
        ]
    },
    {
        "name": "Standoff 2",
        "slug": "standoff-2",
        "short_description": "Mobile FPS - Gold",
        "description": "Standoff 2 - dynamic FPS for mobile. Gold for skins, cases and upgrades.",
        "category": "FPS",
        "logo_url": "/static/images/games/standoff-logo.png",
        "cover_url": "/static/images/games/standoff-cover.jpg",
        "banner_url": "/static/images/games/standoff-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "player_id", "label": "Player ID", "placeholder": "Enter Player ID", "required": True}
        ],
        "products": [
            {"name": "100 Gold", "price": 18000, "cost": 14000},
            {"name": "500 Gold", "price": 85000, "cost": 70000},
            {"name": "1000 Gold", "price": 160000, "cost": 135000},
            {"name": "3000 Gold", "price": 450000, "cost": 380000},
            {"name": "Origin Case x10", "price": 120000, "cost": 95000},
        ]
    },
    {
        "name": "Free Fire",
        "slug": "free-fire",
        "short_description": "Battle royale - Diamonds",
        "description": "Free Fire - fast battle royale. Diamonds for characters, skins and more.",
        "category": "Battle Royale",
        "logo_url": "/static/images/games/free-fire-logo.png",
        "cover_url": "/static/images/games/free-fire-cover.jpg",
        "banner_url": "/static/images/games/free-fire-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "player_id", "label": "Player ID", "placeholder": "Enter Player ID", "required": True}
        ],
        "products": [
            {"name": "100 Diamonds", "price": 15000, "cost": 12000},
            {"name": "310 Diamonds", "price": 45000, "cost": 35000},
            {"name": "520 Diamonds", "price": 75000, "cost": 60000},
            {"name": "1060 Diamonds", "price": 145000, "cost": 120000},
            {"name": "2180 Diamonds", "price": 280000, "cost": 230000},
            {"name": "5600 Diamonds", "price": 680000, "cost": 570000},
        ]
    },
    {
        "name": "Mobile Legends",
        "slug": "mobile-legends",
        "short_description": "MOBA - Diamonds",
        "description": "Mobile Legends: Bang Bang - 5v5 MOBA. Diamonds for heroes and skins.",
        "category": "MOBA",
        "logo_url": "/static/images/games/ml-logo.png",
        "cover_url": "/static/images/games/ml-cover.jpg",
        "banner_url": "/static/images/games/ml-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "player_id", "label": "Player ID", "placeholder": "Enter Player ID", "required": True},
            {"field_key": "server_id", "label": "Server ID", "placeholder": "Enter Server ID", "required": True}
        ],
        "products": [
            {"name": "86 Diamonds", "price": 18000, "cost": 14000},
            {"name": "172 Diamonds", "price": 35000, "cost": 28000},
            {"name": "344 Diamonds", "price": 70000, "cost": 56000},
            {"name": "720 Diamonds", "price": 140000, "cost": 115000},
            {"name": "1446 Diamonds", "price": 270000, "cost": 225000},
        ]
    },
    {
        "name": "Brawl Stars",
        "slug": "brawl-stars",
        "short_description": "3v3 battles - Gems",
        "description": "Brawl Stars - fast multiplayer battles. Gems for Brawl Pass and skins.",
        "category": "Action",
        "logo_url": "/static/images/games/brawl-logo.png",
        "cover_url": "/static/images/games/brawl-cover.jpg",
        "banner_url": "/static/images/games/brawl-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "player_tag", "label": "Player Tag", "placeholder": "#XXXX", "required": True}
        ],
        "products": [
            {"name": "30 Gems", "price": 25000, "cost": 20000},
            {"name": "80 Gems", "price": 60000, "cost": 48000},
            {"name": "170 Gems", "price": 120000, "cost": 95000},
            {"name": "360 Gems", "price": 240000, "cost": 200000},
            {"name": "950 Gems", "price": 600000, "cost": 500000},
        ]
    },
    {
        "name": "Valorant",
        "slug": "valorant",
        "short_description": "Tactical shooter - VP",
        "description": "Valorant - tactical 5v5 shooter. Valorant Points for skins and Battle Pass.",
        "category": "FPS",
        "logo_url": "/static/images/games/valorant-logo.png",
        "cover_url": "/static/images/games/valorant-cover.jpg",
        "banner_url": "/static/images/games/valorant-banner.jpg",
        "featured": True,
        "popular": True,
        "fields": [
            {"field_key": "riot_id", "label": "Riot ID", "placeholder": "Name#Tag", "required": True}
        ],
        "products": [
            {"name": "125 VP", "price": 20000, "cost": 16000},
            {"name": "420 VP", "price": 65000, "cost": 52000},
            {"name": "700 VP", "price": 100000, "cost": 82000},
            {"name": "1375 VP", "price": 190000, "cost": 155000},
            {"name": "2400 VP", "price": 320000, "cost": 265000},
            {"name": "4000 VP", "price": 520000, "cost": 430000},
        ]
    },
    {
        "name": "Fortnite",
        "slug": "fortnite",
        "short_description": "Battle royale - V-Bucks",
        "description": "Fortnite - battle royale and creative. V-Bucks for skins, emotes and Battle Pass.",
        "category": "Battle Royale",
        "logo_url": "/static/images/games/fortnite-logo.png",
        "cover_url": "/static/images/games/fortnite-cover.jpg",
        "banner_url": "/static/images/games/fortnite-banner.jpg",
        "featured": False,
        "popular": True,
        "fields": [
            {"field_key": "epic_id", "label": "Epic ID", "placeholder": "Enter Epic ID", "required": True}
        ],
        "products": [
            {"name": "1000 V-Bucks", "price": 120000, "cost": 95000},
            {"name": "2800 V-Bucks", "price": 300000, "cost": 250000},
            {"name": "5000 V-Bucks", "price": 520000, "cost": 430000},
            {"name": "13500 V-Bucks", "price": 1250000, "cost": 1050000},
        ]
    },
    {
        "name": "League of Legends",
        "slug": "league-of-legends",
        "short_description": "MOBA legend - RP",
        "description": "League of Legends - the world's biggest MOBA. Riot Points for champions and skins.",
        "category": "MOBA",
        "logo_url": "/static/images/games/lol-logo.png",
        "cover_url": "/static/images/games/lol-cover.jpg",
        "banner_url": "/static/images/games/lol-banner.jpg",
        "featured": False,
        "popular": False,
        "fields": [
            {"field_key": "riot_id", "label": "Riot ID", "placeholder": "Name#Tag", "required": True}
        ],
        "products": [
            {"name": "650 RP", "price": 65000, "cost": 52000},
            {"name": "1380 RP", "price": 125000, "cost": 100000},
            {"name": "2800 RP", "price": 240000, "cost": 200000},
            {"name": "5000 RP", "price": 420000, "cost": 350000},
        ]
    },
    {
        "name": "Minecraft",
        "slug": "minecraft",
        "short_description": "Sandbox - Minecoins",
        "description": "Minecraft - endless creativity. Minecoins for marketplace content.",
        "category": "Sandbox",
        "logo_url": "/static/images/games/minecraft-logo.png",
        "cover_url": "/static/images/games/minecraft-cover.jpg",
        "banner_url": "/static/images/games/minecraft-banner.jpg",
        "featured": False,
        "popular": False,
        "fields": [
            {"field_key": "gamertag", "label": "Xbox Gamertag", "placeholder": "Enter Gamertag", "required": True}
        ],
        "products": [
            {"name": "320 Minecoins", "price": 35000, "cost": 28000},
            {"name": "1020 Minecoins", "price": 95000, "cost": 75000},
            {"name": "1720 Minecoins", "price": 160000, "cost": 130000},
            {"name": "3500 Minecoins", "price": 300000, "cost": 250000},
        ]
    },
    {
        "name": "EA Sports FC",
        "slug": "ea-sports-fc",
        "short_description": "Football - FC Points",
        "description": "EA Sports FC - the world's football game. FC Points for Ultimate Team.",
        "category": "Sports",
        "logo_url": "/static/images/games/fc-logo.png",
        "cover_url": "/static/images/games/fc-cover.jpg",
        "banner_url": "/static/images/games/fc-banner.jpg",
        "featured": False,
        "popular": False,
        "fields": [
            {"field_key": "ea_id", "label": "EA ID", "placeholder": "Enter EA ID", "required": True}
        ],
        "products": [
            {"name": "100 FC Points", "price": 18000, "cost": 14000},
            {"name": "500 FC Points", "price": 85000, "cost": 70000},
            {"name": "1050 FC Points", "price": 165000, "cost": 135000},
            {"name": "2200 FC Points", "price": 320000, "cost": 265000},
        ]
    }
]

DONATION_PRESETS = [10000, 25000, 50000, 100000, 250000, 500000, 1000000]

async def seed_all(db: AsyncSession):
    try:
        # Roles
        for role_name in ["user", "admin", "seller"]:
            result = await db.execute(select(Role).where(Role.name == role_name))
            if not result.scalar_one_or_none():
                db.add(Role(name=role_name, description=f"{role_name} role"))

        await db.flush()

        # Game categories
        categories = {}
        cat_names = ["Battle Royale", "FPS", "MOBA", "Strategy", "Sandbox", "Action", "Sports"]
        for cat_name in cat_names:
            result = await db.execute(select(GameCategory).where(GameCategory.slug == slugify(cat_name)))
            cat = result.scalar_one_or_none()
            if not cat:
                cat = GameCategory(name=cat_name, slug=slugify(cat_name), description=f"{cat_name} games")
                db.add(cat)
                await db.flush()
            categories[cat_name] = cat

        # Supplier
        result = await db.execute(select(Supplier).where(Supplier.code == "MANUAL"))
        supplier = result.scalar_one_or_none()
        if not supplier:
            supplier = Supplier(name="Manual Fulfillment", code="MANUAL", is_active=True, config={"type": "manual"})
            db.add(supplier)
            await db.flush()

        # Games and products
        for game_data in GAMES_DATA:
            result = await db.execute(select(Game).where(Game.slug == game_data["slug"]))
            game = result.scalar_one_or_none()
            if not game:
                cat = categories.get(game_data["category"])
                game = Game(
                    name=game_data["name"],
                    slug=game_data["slug"],
                    description=game_data["description"],
                    short_description=game_data["short_description"],
                    logo_url=game_data["logo_url"],
                    cover_url=game_data["cover_url"],
                    banner_url=game_data["banner_url"],
                    category_id=cat.id if cat else None,
                    featured=game_data.get("featured", False),
                    popular=game_data.get("popular", False),
                    status="ACTIVE",
                    sort_order=0,
                    supplier_id=supplier.id
                )
                db.add(game)
                await db.flush()

                # Fields
                for field_data in game_data.get("fields", []):
                    field = GameField(
                        game_id=game.id,
                        field_key=field_data["field_key"],
                        label=field_data["label"],
                        placeholder=field_data.get("placeholder"),
                        field_type=field_data.get("field_type", "text"),
                        required=field_data.get("required", True),
                        sort_order=0
                    )
                    db.add(field)

                # Products
                for prod in game_data.get("products", []):
                    prod_slug = slugify(f"{game_data['slug']}-{prod['name']}")
                    result = await db.execute(select(Product).where(Product.slug == prod_slug))
                    if not result.scalar_one_or_none():
                        product = Product(
                            name=f"{game_data['name']} - {prod['name']}",
                            slug=prod_slug,
                            description=f"{prod['name']} for {game_data['name']}",
                            game_id=game.id,
                            supplier_id=supplier.id,
                            supplier_cost=Decimal(str(prod["cost"])),
                            customer_price=Decimal(str(prod["price"])),
                            currency="UZS",
                            featured=False,
                            popular=True if "UC" in prod["name"] or "Robux" in prod["name"] or "Gems" in prod["name"] else False,
                            is_active=True,
                            stock_status="IN_STOCK",
                            sort_order=0,
                            image_url=game_data["logo_url"]
                        )
                        db.add(product)

        # Donation presets
        for i, amount in enumerate(DONATION_PRESETS):
            result = await db.execute(select(DonationPreset).where(DonationPreset.amount == amount))
            if not result.scalar_one_or_none():
                preset = DonationPreset(amount=Decimal(str(amount)), currency="UZS", label=f"{amount:,} UZS", sort_order=i, is_active=True)
                db.add(preset)

        # Donation profiles - create dummy users first
        # Create a test user for donations if not exists
        result = await db.execute(select(User).where(User.username == "streamer_uz"))
        donor_user = result.scalar_one_or_none()
        if not donor_user:
            donor_user = User(
                username="streamer_uz",
                email="streamer@example.com",
                password_hash=hash_password("Test123!@#"),
                display_name="Streamer UZ",
                status="ACTIVE",
                is_verified=True
            )
            db.add(donor_user)
            await db.flush()

        profiles_data = [
            {"username": "gamer_uz", "display_name": "Gamer UZ", "bio": "Professional PUBG Mobile streamer from Uzbekistan. Support my channel!", "goal": 5000000},
            {"username": "pro_player", "display_name": "Pro Player", "bio": "Esports player, Valorant and CS2. Your support helps me compete!", "goal": 10000000},
            {"username": "art_creator", "display_name": "Art Creator", "bio": "Digital artist creating gaming art. Support my work!", "goal": 3000000},
        ]

        for pdata in profiles_data:
            result = await db.execute(select(DonationProfile).where(DonationProfile.username == pdata["username"]))
            if not result.scalar_one_or_none():
                profile = DonationProfile(
                    user_id=donor_user.id,
                    username=pdata["username"],
                    display_name=pdata["display_name"],
                    bio=pdata["bio"],
                    avatar_url="/static/images/avatars/default.png",
                    cover_url="/static/images/covers/default.jpg",
                    goal_amount=Decimal(str(pdata["goal"])),
                    current_amount=Decimal("0"),
                    is_active=True
                )
                db.add(profile)

        # Marketplace categories
        mp_cats = [
            {"name": "Game Accounts", "slug": "game-accounts", "commission": 10},
            {"name": "Skins & Items", "slug": "skins-items", "commission": 8},
            {"name": "Boosting Services", "slug": "boosting", "commission": 12},
            {"name": "Gift Cards", "slug": "gift-cards", "commission": 5},
        ]
        for cat_data in mp_cats:
            result = await db.execute(select(MarketplaceCategory).where(MarketplaceCategory.slug == cat_data["slug"]))
            if not result.scalar_one_or_none():
                cat = MarketplaceCategory(
                    name=cat_data["name"],
                    slug=cat_data["slug"],
                    commission_rate=Decimal(str(cat_data["commission"])),
                    is_active=True
                )
                db.add(cat)

        # Promotions
        promos = [
            {"title": "Welcome Bonus", "slug": "welcome-bonus", "description": "Get 10% off your first purchase! Use code WELCOME10", "featured": True},
            {"title": "PUBG UC Sale", "slug": "pubg-sale", "description": "Up to 20% bonus UC on PUBG Mobile top-ups this week!", "featured": True},
            {"title": "Roblox Week", "slug": "roblox-week", "description": "Special Robux discounts - limited time!", "featured": True},
        ]
        for promo_data in promos:
            result = await db.execute(select(Promotion).where(Promotion.slug == promo_data["slug"]))
            if not result.scalar_one_or_none():
                promo = Promotion(
                    title=promo_data["title"],
                    slug=promo_data["slug"],
                    description=promo_data["description"],
                    featured=promo_data["featured"],
                    is_active=True,
                    promotion_type="GENERAL"
                )
                db.add(promo)

        # Settings
        settings_data = [
            {"key": "site_name", "value": "VYRON", "description": "Site name", "is_public": True},
            {"key": "site_description", "value": "Premium gaming commerce and digital marketplace", "description": "Site description", "is_public": True},
            {"key": "maintenance_mode", "value": "false", "description": "Maintenance mode", "is_public": False},
        ]
        for sdata in settings_data:
            result = await db.execute(select(Setting).where(Setting.key == sdata["key"]))
            if not result.scalar_one_or_none():
                s = Setting(key=sdata["key"], value=sdata["value"], description=sdata["description"], is_public=sdata["is_public"])
                db.add(s)

        await db.commit()
        logger.info("Seed data created successfully")

    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        await db.rollback()
        raise
