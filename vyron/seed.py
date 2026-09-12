"""Development seed.

Creates:
- the SUPER_ADMIN account from ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_USERNAME env vars,
- default platform settings rows,
- seller subscription plans,
- (only when SEED_DEMO_DATA=1) a demo catalog: games, products, variants, a welcome
  coupon and marketplace promotions.

NEVER seeds fake financial data: no orders, no payments, no donations, no revenue
ledger entries, no completed deliveries. Real money rows only ever come from real
verified events.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.models import (
    Coupon,
    Game,
    Product,
    ProductVariant,
    Promotion,
    SellerSubscriptionPlan,
    User,
)
from vyron.enums import (
    CouponType,
    GameStatus,
    ProductType,
    PromotionKind,
    UserRole,
    UserStatus,
)
from vyron.i18n import DEFAULT_LANGUAGE
from vyron.logging import get_logger
from vyron.security.hashing import hash_password
from vyron.services import settings_service

log = get_logger("vyron.seed")


def seed_admin(db: DbSession) -> User:
    if not settings.admin_email or not settings.admin_password:
        raise RuntimeError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must be set to create the initial super admin."
        )
    admin = db.scalar(select(User).where(User.email == settings.admin_email))
    if admin is None:
        admin = User(
            name="VYRON Admin",
            username=settings.admin_username or "vyron_admin",
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.SUPER_ADMIN.value,
            status=UserStatus.ACTIVE.value,
            email_verified=True,
            locale=DEFAULT_LANGUAGE,
            theme="dark",
        )
        db.add(admin)
        db.commit()
        log.info("super admin created", email=admin.email, username=admin.username)
    else:
        changed = False
        if admin.role != UserRole.SUPER_ADMIN.value:
            admin.role = UserRole.SUPER_ADMIN.value
            changed = True
        if admin.status != UserStatus.ACTIVE.value:
            admin.status = UserStatus.ACTIVE.value
            changed = True
        if changed:
            db.commit()
        log.info("super admin already exists", email=admin.email)
    return admin


def seed_settings(db: DbSession) -> None:
    n = settings_service.ensure_defaults(db)
    db.commit()
    if n:
        log.info("platform settings seeded", count=n)


SUBSCRIPTION_PLANS: List[Dict[str, Any]] = [
    {
        "code": "STARTER",
        "name": "Starter",
        "description": "Basic seller tools: listings, manual delivery, payouts.",
        "price": Decimal("0.00"),
        "period_days": 30,
        "features": ["unlimited_listings", "manual_delivery", "standard_support"],
    },
    {
        "code": "PRO",
        "name": "Pro Seller",
        "description": "Reduced commission, promoted-listing credits and priority support.",
        "price": Decimal("19.00"),
        "period_days": 30,
        "features": ["commission_discount_pct:20", "promotion_credits:2", "priority_support", "advanced_stats"],
    },
    {
        "code": "BUSINESS",
        "name": "Business",
        "description": "Lowest commission, bulk tools, homepage promotion credits, account manager.",
        "price": Decimal("49.00"),
        "period_days": 30,
        "features": ["commission_discount_pct:35", "promotion_credits:6", "homepage_credit:1", "api_access", "account_manager"],
    },
]


def seed_subscription_plans(db: DbSession) -> None:
    created = 0
    for plan in SUBSCRIPTION_PLANS:
        exists = db.scalar(select(SellerSubscriptionPlan).where(SellerSubscriptionPlan.code == plan["code"]))
        if exists is not None:
            exists.name = plan["name"]
            exists.description = plan["description"]
            exists.price = plan["price"]
            exists.period_days = plan["period_days"]
            exists.features = plan["features"]
            exists.active = True
            continue
        db.add(
            SellerSubscriptionPlan(
                code=plan["code"],
                name=plan["name"],
                description=plan["description"],
                price=plan["price"],
                currency="USD",
                period_days=plan["period_days"],
                features=plan["features"],
                active=True,
            )
        )
        created += 1
    db.commit()
    if created:
        log.info("seller subscription plans seeded", count=created)


def _field(key: str, label: str, ftype: str = "text", required: bool = True, **extra) -> Dict[str, Any]:
    data: Dict[str, Any] = {"name": key, "key": key, "label": label, "type": ftype, "required": required}
    data.update(extra)
    return data


DEMO_GAMES: List[Dict[str, Any]] = [
    {
        "name": "PUBG MOBILE",
        "slug": "pubg-mobile",
        "description": "UC top-ups delivered instantly to your PUBG MOBILE player ID.",
        "accent_color": "#f2a900",
        "is_featured": True,
        "required_fields": [_field("player_id", "Player ID", "text", True, pattern="^\\d{6,15}$", placeholder="12-digit numeric ID")],
        "products": [
            {
                "name": "PUBG Mobile UC Top-Up",
                "slug": "pubg-mobile-uc",
                "type": ProductType.TOPUP.value,
                "is_featured": True,
                "variants": [
                    ("60 UC", Decimal("0.99"), Decimal("1.39")),
                    ("325 UC", Decimal("4.49"), Decimal("5.99")),
                    ("660 UC", Decimal("8.49"), Decimal("10.99")),
                    ("1800 UC", Decimal("21.99"), Decimal("27.99")),
                ],
            },
        ],
    },
    {
        "name": "Free Fire",
        "slug": "free-fire",
        "description": "Diamonds for Free Fire — enter your numeric player ID.",
        "accent_color": "#ff6b35",
        "is_featured": True,
        "required_fields": [_field("player_id", "Player ID", "text", True, pattern="^\\d{6,14}$")],
        "products": [
            {
                "name": "Free Fire Diamonds",
                "slug": "free-fire-diamonds",
                "type": ProductType.TOPUP.value,
                "is_featured": True,
                "variants": [
                    ("100 Diamonds", Decimal("0.89"), Decimal("1.19")),
                    ("310 Diamonds", Decimal("2.49"), Decimal("3.29")),
                    ("520 Diamonds", Decimal("3.99"), Decimal("5.19")),
                    ("1060 Diamonds", Decimal("7.49"), Decimal("9.49")),
                ],
            },
        ],
    },
    {
        "name": "Roblox",
        "slug": "roblox",
        "description": "Robux top-ups and gift cards for Roblox.",
        "accent_color": "#e2231a",
        "is_featured": False,
        "required_fields": [_field("username", "Roblox username", "text", True)],
        "products": [
            {
                "name": "Robux Top-Up",
                "slug": "robux-topup",
                "type": ProductType.TOPUP.value,
                "variants": [
                    ("400 Robux", Decimal("4.49"), Decimal("5.79")),
                    ("800 Robux", Decimal("8.49"), Decimal("10.49")),
                    ("1700 Robux", Decimal("16.99"), Decimal("20.99")),
                ],
            },
            {
                "name": "Roblox Gift Card",
                "slug": "roblox-gift-card",
                "type": ProductType.GIFT_CARD.value,
                "variants": [("$10 Gift Card", Decimal("9.60"), Decimal("10.99")), ("$25 Gift Card", Decimal("23.90"), Decimal("26.49"))],
            },
        ],
    },
    {
        "name": "Steam",
        "slug": "steam",
        "description": "Steam wallet top-ups by account name.",
        "accent_color": "#1b2838",
        "is_featured": True,
        "required_fields": [
            _field("steam_account", "Steam login", "text", True),
            _field("region", "Wallet region", "select", True, options=["us", "eu", "asia"]),
        ],
        "products": [
            {
                "name": "Steam Wallet Top-Up",
                "slug": "steam-wallet",
                "type": ProductType.TOPUP.value,
                "variants": [("$5 Wallet", Decimal("4.85"), Decimal("5.99")), ("$10 Wallet", Decimal("9.60"), Decimal("11.49")), ("$20 Wallet", Decimal("19.10"), Decimal("22.49"))],
            }
        ],
    },
]


def _upsert_game(db: DbSession, data: Dict[str, Any], order: int) -> Game:
    game = db.scalar(select(Game).where(Game.slug == data["slug"]))
    if game is None:
        game = Game(slug=data["slug"])
        db.add(game)
    game.name = data["name"]
    game.description = data.get("description")
    game.accent_color = data.get("accent_color")
    game.status = GameStatus.ACTIVE.value
    game.is_featured = data.get("is_featured", False)
    game.sort_order = order
    game.required_fields = data.get("required_fields")
    db.flush()
    return game


def _upsert_product(db: DbSession, game: Game, data: Dict[str, Any], order: int) -> Product:
    product = db.scalar(select(Product).where(Product.slug == data["slug"]))
    if product is None:
        product = Product(slug=data["slug"], game_id=game.id)
        db.add(product)
    product.game_id = game.id
    product.name = data["name"]
    product.type = data["type"]
    product.description = data.get("description")
    product.active = True
    product.is_featured = data.get("is_featured", False)
    product.sort_order = order
    product.required_fields = data.get("required_fields")  # inherits game schema when None
    db.flush()

    for i, (vname, cost, price) in enumerate(data.get("variants", [])):
        variant = db.scalar(
            select(ProductVariant).where(ProductVariant.product_id == product.id, ProductVariant.name == vname)
        )
        if variant is None:
            variant = ProductVariant(product_id=product.id, name=vname)
            db.add(variant)
        variant.cost_price = cost
        variant.selling_price = price
        variant.currency = "USD"
        variant.active = True
        variant.stock = -1  # unlimited (digital)
        variant.sort_order = i
    db.flush()
    return product


def seed_demo_catalog(db: DbSession) -> None:
    if not settings.seed_demo_data:
        log.info("SEED_DEMO_DATA disabled — skipping demo catalog")
        return

    for i, game_data in enumerate(DEMO_GAMES):
        game = _upsert_game(db, game_data, i)
        for j, product_data in enumerate(game_data.get("products", [])):
            _upsert_product(db, game, product_data, j)

    coupon = db.scalar(select(Coupon).where(Coupon.code == "WELCOME10"))
    if coupon is None:
        db.add(
            Coupon(
                code="WELCOME10",
                type=CouponType.PERCENTAGE.value,
                value=Decimal("10.00"),
                currency="USD",
                max_discount=Decimal("5.00"),
                max_uses=1000,
                per_user_limit=1,
                min_order_amount=Decimal("5.00"),
                active=True,
            )
        )

    promos = [
        {
            "title": "Instant game top-ups",
            "slug": "instant-topups",
            "description": "Top up PUBG Mobile, Free Fire, Roblox and Steam — delivery starts seconds after payment is verified.",
            "kind": PromotionKind.HOMEPAGE.value,
            "target_url": "/games",
            "badge_text": "HOT",
        },
        {
            "title": "Sell on VYRON Marketplace",
            "slug": "become-seller",
            "description": "List accounts, items and gift cards. Transparent commission, scheduled payouts.",
            "kind": PromotionKind.HOMEPAGE.value,
            "target_url": "/seller/apply",
            "badge_text": "NEW",
        },
    ]
    for i, p in enumerate(promos):
        promo = db.scalar(select(Promotion).where(Promotion.slug == p["slug"]))
        if promo is None:
            promo = Promotion(slug=p["slug"])
            db.add(promo)
        promo.title = p["title"]
        promo.description = p["description"]
        promo.kind = p["kind"]
        promo.target_url = p["target_url"]
        promo.badge_text = p["badge_text"]
        promo.active = True
        promo.sort_order = i

    db.commit()
    games = db.scalar(select(Game).where(Game.slug == DEMO_GAMES[0]["slug"]))
    log.info("demo catalog seeded", games=len(DEMO_GAMES), first_game=games.slug if games else None)


def run_seed(db: DbSession) -> None:
    seed_settings(db)
    seed_admin(db)
    seed_subscription_plans(db)
    seed_demo_catalog(db)
    log.info("seed complete")


def main() -> None:
    from vyron.db.base import get_session_factory

    db = get_session_factory()()
    try:
        run_seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
