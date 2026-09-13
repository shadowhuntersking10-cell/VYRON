"""Seed catalog data (games, products, presets, promos). No fake transactions."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.services.pricing import quote
from app.utils.logging import get_logger

log = get_logger("vyron.seed")

# slug, name, (gradient colors), initials, category, description
GAMES = [
    ("pubg-mobile", "PUBG Mobile", ("#3b2f1e", "#c98a1b"), "PM", "battle-royale",
     "PUBG Mobile UC top-ups: Unknown Cash for crates, passes and skins."),
    ("roblox", "Roblox", ("#1c1c22", "#e2231a"), "RB", "sandbox",
     "Robux for avatars, game passes and premium items."),
    ("clash-of-clans", "Clash of Clans", ("#3a2a12", "#f5b301"), "CC", "strategy",
     "Gems and Gold Pass for your village."),
    ("clash-royale", "Clash Royale", ("#0f2a52", "#2f80ed"), "CR", "strategy",
     "Gems and Pass Royale for the arena."),
    ("counter-strike-2", "Counter-Strike 2", ("#2b2b2b", "#de9b35"), "CS", "shooter",
     "Steam wallet codes, Prime and passes for CS2 players."),
    ("standoff-2", "Standoff 2", ("#232a35", "#5ac8fa"), "S2", "shooter",
     "Gold, cases and keys for Standoff 2."),
    ("free-fire", "Free Fire", ("#3d1d00", "#ff6a00"), "FF", "battle-royale",
     "Diamonds for characters, bundles and Booyah Pass."),
    ("mobile-legends", "Mobile Legends", ("#101a3a", "#3f6cff"), "ML", "moba",
     "Diamonds and Twilight Pass for MLBB heroes and skins."),
    ("brawl-stars", "Brawl Stars", ("#4a1d00", "#ffb300"), "BS", "action",
     "Gems and Brawl Pass for brawlers and skins."),
    ("valorant", "Valorant", ("#2a0a12", "#ff4655"), "VL", "shooter",
     "Valorant Points for skins, agents and battle pass."),
    ("fortnite", "Fortnite", ("#231245", "#9d4edd"), "FN", "battle-royale",
     "V-Bucks and Crew for outfits and Battle Pass."),
    ("league-of-legends", "League of Legends", ("#0a1428", "#c89b3c"), "LL", "moba",
     "Riot Points for champions, skins and event passes."),
    ("minecraft", "Minecraft", ("#1d3a1a", "#5dff4d"), "MC", "sandbox",
     "Minecoins, Realms and content packs."),
    ("ea-sports-fc", "EA Sports FC", ("#062b16", "#00e676"), "FC", "sports",
     "FC Points for Ultimate Team packs and drafts."),
]

# game_slug -> list of (product name, supplier_cost UZS)
PRODUCTS: dict[str, list[tuple[str, int]]] = {
    "pubg-mobile": [("60 UC", 12500), ("325 UC", 62000), ("660 UC", 124000), ("1800 UC", 310000),
                    ("3850 UC", 620000), ("8100 UC", 1240000)],
    "roblox": [("400 Robux", 62000), ("800 Robux", 124000), ("1700 Robux", 248000),
               ("4500 Robux", 620000), ("10000 Robux", 1240000)],
    "clash-of-clans": [("80 Gems", 12500), ("500 Gems", 62000), ("1200 Gems", 124000),
                       ("2500 Gems", 248000), ("6500 Gems", 620000), ("Gold Pass", 90000)],
    "clash-royale": [("80 Gems", 12500), ("500 Gems", 62000), ("1200 Gems", 124000),
                     ("2500 Gems", 248000), ("6500 Gems", 620000)],
    "counter-strike-2": [("Steam Wallet $5", 65000), ("Steam Wallet $10", 130000),
                         ("Steam Wallet $20", 260000), ("Prime Status", 190000),
                         ("Operation Pass", 190000)],
    "standoff-2": [("100 Gold", 16000), ("500 Gold", 75000), ("1000 Gold", 145000),
                   ("3000 Gold", 420000), ("Case Key x5", 60000)],
    "free-fire": [("100 Diamonds", 12500), ("310 Diamonds", 37000), ("520 Diamonds", 62000),
                  ("1060 Diamonds", 124000), ("2180 Diamonds", 248000), ("5600 Diamonds", 620000)],
    "mobile-legends": [("86 Diamonds", 16000), ("172 Diamonds", 32000), ("257 Diamonds", 47000),
                       ("344 Diamonds", 62000), ("514 Diamonds", 93000), ("706 Diamonds", 124000),
                       ("1050 Diamonds", 186000), ("Twilight Pass", 124000)],
    "brawl-stars": [("80 Gems", 25000), ("170 Gems", 50000), ("360 Gems", 100000),
                    ("950 Gems", 250000), ("2000 Gems", 500000), ("Brawl Pass", 90000)],
    "valorant": [("475 VP", 62000), ("1000 VP", 124000), ("2050 VP", 248000),
                 ("3650 VP", 434000), ("5350 VP", 620000), ("11000 VP", 1240000)],
    "fortnite": [("1000 V-Bucks", 110000), ("2800 V-Bucks", 280000), ("5000 V-Bucks", 470000),
                 ("13500 V-Bucks", 1240000), ("Fortnite Crew 1 month", 150000)],
    "league-of-legends": [("650 RP", 62000), ("1380 RP", 124000), ("2800 RP", 248000),
                          ("5800 RP", 496000), ("10000 RP", 868000)],
    "minecraft": [("320 Minecoins", 25000), ("1020 Minecoins", 75000), ("1720 Minecoins", 124000),
                  ("3500 Minecoins", 248000), ("8000 Minecoins", 550000), ("Realms Plus 1 month", 100000)],
    "ea-sports-fc": [("100 FC Points", 16000), ("520 FC Points", 75000), ("1050 FC Points", 145000),
                     ("2200 FC Points", 290000), ("4600 FC Points", 600000), ("12000 FC Points", 1500000)],
}

GAME_FIELDS = [
    ("player_id", "Player ID", "text", True, "e.g. 5123456789"),
    ("region", "Region", "text", False, "e.g. Europe / Asia"),
    ("nickname", "Nickname", "text", False, "In-game nickname"),
]

PRESETS = [10000, 25000, 50000, 100000, 250000, 500000, 1000000]

CATEGORIES = [("topup", "Top-Up"), ("currency", "Currency"), ("giftcard", "Gift Cards"), ("digital", "Digital Goods")]
GAME_CATS = [("battle-royale", "Battle Royale"), ("shooter", "Shooter"), ("moba", "MOBA"),
             ("strategy", "Strategy"), ("sandbox", "Sandbox"), ("action", "Action"), ("sports", "Sports")]
MP_CATS = [("accounts", "Game Accounts"), ("items", "Items & Skins"), ("boost", "Boosting"),
           ("giftcards", "Gift Cards"), ("subscriptions", "Subscriptions")]


def _svg(path: Path, c1: str, c2: str, text: str, sub: str, w: int = 512, h: int = 512):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    fs = int(min(w, h) * 0.34)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient>'
        f'<radialGradient id="r" cx="0.5" cy="0.35" r="0.8">'
        f'<stop offset="0" stop-color="#ffffff" stop-opacity="0.25"/>'
        f'<stop offset="1" stop-color="#000000" stop-opacity="0.25"/></radialGradient></defs>'
        f'<rect width="{w}" height="{h}" rx="{int(min(w,h)*0.18)}" fill="url(#g)"/>'
        f'<rect width="{w}" height="{h}" rx="{int(min(w,h)*0.18)}" fill="url(#r)"/>'
        f'<text x="50%" y="52%" text-anchor="middle" dominant-baseline="middle" '
        f'font-family="Arial,Helvetica,sans-serif" font-weight="900" font-size="{fs}" fill="#ffffff" '
        f'fill-opacity="0.95" letter-spacing="2">{text}</text>'
        f'<text x="50%" y="88%" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" '
        f'font-size="{int(min(w,h)*0.07)}" fill="#ffffff" fill-opacity="0.85">{sub}</text>'
        f'</svg>', encoding="utf-8")


def _price(cost: int) -> tuple[int, int]:
    from app.config import settings
    q = quote(cost, payment_fee_percent=settings.PAYMENT_FEE_PERCENT,
              payment_fee_fixed=settings.PAYMENT_FEE_FIXED,
              safety_buffer_percent=settings.SAFETY_BUFFER_PERCENT,
              platform_margin_percent=settings.PLATFORM_MARGIN_PERCENT,
              minimum_margin_percent=settings.MINIMUM_MARGIN_PERCENT,
              platform_fee_percent=settings.PLATFORM_FEE_PERCENT)
    return int(q["minimum_safe_price"]), int(q["suggested_price"])


def seed(db: Session) -> dict:
    stats = {"games": 0, "products": 0}
    root = Path(__file__).resolve().parent.parent
    imgdir = root / "static" / "images" / "games"

    for name in ("user", "seller", "admin"):
        if not db.query(models.Role).filter_by(name=name).first():
            db.add(models.Role(name=name))

    cat_map = {}
    for slug, name in GAME_CATS:
        c = db.query(models.GameCategory).filter_by(slug=slug).first()
        if not c:
            c = models.GameCategory(name=name, slug=slug)
            db.add(c)
            db.flush()
        cat_map[slug] = c.id

    for slug, name, (c1, c2), initials, cat, desc in GAMES:
        logo_p = imgdir / f"{slug}-logo.svg"
        cover_p = imgdir / f"{slug}-cover.svg"
        banner_p = imgdir / f"{slug}-banner.svg"
        _svg(logo_p, c1, c2, initials, name)
        _svg(cover_p, c1, c2, initials, name)
        _svg(banner_p, c1, c2, initials, name, w=1200, h=400)
        g = db.query(models.Game).filter_by(slug=slug).first()
        if not g:
            g = models.Game(name=name, slug=slug, description=desc,
                            logo=f"/static/images/games/{logo_p.name}",
                            cover=f"/static/images/games/{cover_p.name}",
                            banner=f"/static/images/games/{banner_p.name}",
                            category_id=cat_map.get(cat), status="active",
                            featured=slug in ("pubg-mobile", "roblox", "free-fire", "valorant"),
                            popular=slug in ("pubg-mobile", "roblox", "free-fire", "mobile-legends",
                                             "valorant", "brawl-stars"),
                            seo_title=f"{name} top-up — VYRON",
                            seo_description=f"Buy {name} top-ups and digital goods on VYRON.")
            db.add(g)
            db.flush()
            for i, (key, label, ftype, req, ph) in enumerate(GAME_FIELDS):
                db.add(models.GameField(game_id=g.id, key=key, label=label, field_type=ftype,
                                        required=req, placeholder=ph, sort_order=i))
            stats["games"] += 1
        for pname, cost in PRODUCTS.get(slug, []):
            pslug = f"{slug}-{''.join(c.lower() if c.isalnum() else '-' for c in pname).strip('-')}"
            if db.query(models.Product).filter_by(slug=pslug).first():
                continue
            _, suggested = _price(cost)
            db.add(models.Product(
                game_id=g.id, name=f"{name} — {pname}", slug=pslug,
                description=f"{pname} for {name}. Delivered after verified payment.",
                category="topup", supplier_cost=cost, currency="UZS",
                customer_price=suggested, status="active", stock_status="in_stock",
                image=g.logo, popular=pname.split()[0] in ("60", "325", "660", "400", "800",
                      "100", "310", "520", "86", "475", "1000", "80", "170", "650"),
                featured=False))
            stats["products"] += 1

    for slug, name in MP_CATS:
        if not db.query(models.MarketplaceCategory).filter_by(slug=slug).first():
            db.add(models.MarketplaceCategory(name=name, slug=slug))

    for i, amount in enumerate(PRESETS):
        if not db.query(models.DonationPreset).filter_by(amount=amount).first():
            db.add(models.DonationPreset(amount=amount, sort_order=i))

    promos = [
        ("welcome10", "Welcome bonus — 10% off first top-up",
         "Use coupon WELCOME10 at checkout.", "/static/images/promo-welcome.svg", "/games"),
        ("pubg-season", "PUBG Mobile season sale",
         "Best UC prices this season.", "/static/images/promo-pubg.svg", "/games/pubg-mobile"),
        ("market-launch", "Marketplace is live",
         "Sell game goods to thousands of players.", "/static/images/promo-market.svg", "/marketplace"),
    ]
    for slug, title, desc, banner, url in promos:
        if not db.query(models.Promotion).filter_by(slug=slug).first():
            _svg(root / "static" / "images" / Path(banner).name, "#0B1F3A", "#2563EB",
                 "VYRON", title[:24], w=1200, h=400)
            db.add(models.Promotion(title=title, slug=slug, description=desc, banner=banner,
                                    target_url=url, is_active=True))
    if not db.query(models.Coupon).filter_by(code="WELCOME10").first():
        db.add(models.Coupon(code="WELCOME10", kind="percent", value=10, per_user_limit=1, is_active=True))

    if not db.query(models.Supplier).filter_by(code="manual").first():
        db.add(models.Supplier(name="Manual fulfillment", code="manual", adapter="manual", is_active=True))

    defaults = {
        "site_name": "VYRON",
        "support_email": "support@vyron.example.com",
        "donation_fee_percent": "5.0",
        "marketplace_commission_percent": "10.0",
    }
    for k, v in defaults.items():
        if not db.query(models.Setting).filter_by(key=k).first():
            db.add(models.Setting(key=k, value=v))

    # demo donation creators + seller showcase (catalog seed, zero transactions)
    from app.utils.security import hash_password
    seed_users = [("vyron_official", "official@vyron.example.com", "VYRON Official"),
                  ("gamer_uz", "gamer@vyron.example.com", "Gamer UZ"),
                  ("streamer_pro", "streamer@vyron.example.com", "Streamer Pro")]
    for uname, email, disp in seed_users:
        u = db.query(models.User).filter_by(username=uname).first()
        if not u:
            u = models.User(username=uname, email=email, password_hash=hash_password("Seed-" + uname + "-2026!x"),
                            display_name=disp, lang="uz")
            db.add(u)
            db.flush()
            role = db.query(models.Role).filter_by(name="user").first()
            db.add(models.UserRole(user_id=u.id, role_id=role.id))
            db.add(models.Wallet(user_id=u.id))
            db.flush()
            av = root / "static" / "images" / f"avatar-{uname}.svg"
            cv = root / "static" / "images" / f"cover-{uname}.svg"
            _svg(av, "#0B1F3A", "#60A5FA", disp[:2].upper(), disp, w=256, h=256)
            _svg(cv, "#071426", "#2563EB", "VYRON", disp, w=1200, h=400)
            db.add(models.DonationProfile(
                user_id=u.id, username=uname, display_name=disp,
                bio=f"Support {disp} — donations help create more content.",
                avatar=f"/static/images/{av.name}", cover=f"/static/images/{cv.name}",
                goal_amount=5000000, raised_amount=0, is_active=True))
    db.commit()
    log.info("seed done: %s", stats)
    return stats
