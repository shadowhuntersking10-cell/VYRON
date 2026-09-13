"""HTML pages (Jinja2): public site, user dashboard, admin panel, mini app."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import template_context, templates
from app.auth.deps import _user_from_token, _extract_token  # noqa: PLC2701 - page helpers
from app.config import settings
from app.database import get_db
from app.models import DonationProfile, Game, MarketplaceListing, Product, Promotion, Seller
from app.services import catalog_service, donation_service

router = APIRouter(tags=["pages"])


async def _ctx(request: Request, db: AsyncSession, **extra) -> dict:
    user = await _user_from_token(db, _extract_token(request))
    ctx = template_context(request, user=user,
                           is_admin=bool(user and user.role == "ADMIN"))
    ctx.update(extra)
    return ctx


def _page(template: str):
    async def handler(request: Request, db: AsyncSession = Depends(get_db)):
        return templates.TemplateResponse(request, template, await _ctx(request, db))

    return handler


# ---------- public ----------
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    games = await catalog_service.list_games(db)
    promos = (await db.execute(select(Promotion).where(Promotion.is_active.is_(True)).limit(5))).scalars().all()
    listings = (await db.execute(select(MarketplaceListing).where(MarketplaceListing.status == "active")
                                 .order_by(MarketplaceListing.is_promoted.desc(), MarketplaceListing.id.desc()).limit(8))).scalars().all()
    profiles = (await db.execute(select(DonationProfile).where(DonationProfile.is_active.is_(True)).limit(4))).scalars().all()
    popular = (await db.execute(select(Product).where(Product.is_active.is_(True), Product.is_popular.is_(True)).order_by(Product.id).limit(8))).scalars().all()
    return templates.TemplateResponse(request, "public/index.html", await _ctx(
        request, db, games=games[:8], promos=list(promos), listings=list(listings), profiles=list(profiles), popular=list(popular)))


@router.get("/games", response_class=HTMLResponse)
async def games_page(request: Request, db: AsyncSession = Depends(get_db)):
    games = await catalog_service.list_games(db)
    cats = await catalog_service.categories(db)
    return templates.TemplateResponse(request, "public/games.html", await _ctx(request, db, games=games, categories=cats))


@router.get("/games/{slug}", response_class=HTMLResponse)
async def game_detail(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    game = await catalog_service.get_game_by_slug(db, slug)
    if not game:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    products = await catalog_service.list_products_for_game(db, game.id)
    return templates.TemplateResponse(request, "public/game_detail.html", await _ctx(request, db, game=game, products=products))


@router.get("/products/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    product = await catalog_service.get_product(db, product_id)
    if not product:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    game = await db.get(Game, product.game_id)
    return templates.TemplateResponse(request, "public/product_detail.html", await _ctx(request, db, product=product, game=game))


@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "public/marketplace.html", await _ctx(request, db))


@router.get("/marketplace/{listing_id}", response_class=HTMLResponse)
async def marketplace_detail(request: Request, listing_id: int, db: AsyncSession = Depends(get_db)):
    listing = await db.get(MarketplaceListing, listing_id)
    if not listing or listing.status == "deleted":
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    seller = await db.get(Seller, listing.seller_id)
    from app.models import ListingImage as _LI
    gallery = (await db.execute(select(_LI).where(_LI.listing_id == listing.id)
                                .order_by(_LI.sort_order))).scalars().all()
    return templates.TemplateResponse(request, "public/marketplace_detail.html", await _ctx(request, db, listing=listing, seller=seller, gallery=list(gallery)))


@router.get("/seller/{username}", response_class=HTMLResponse)
async def seller_shop_by_username(request: Request, username: str, db: AsyncSession = Depends(get_db)):
    """Public mini-shop page addressed by the seller's account username."""
    from app.models import MarketplaceListing as _L
    from app.models import Review as _R
    from app.models import User as _U
    user = (await db.execute(select(_U).where(_U.username == username))).scalars().first()
    seller = None
    if user:
        seller = (await db.execute(select(Seller).where(Seller.user_id == user.id))).scalars().first()
    if not seller or not seller.is_active:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    listings = (await db.execute(select(_L).where(_L.seller_id == seller.id, _L.status == "active").order_by(_L.id.desc()).limit(24))).scalars().all()
    reviews = (await db.execute(select(_R).where(_R.seller_id == seller.id).order_by(_R.id.desc()).limit(20))).scalars().all()
    return templates.TemplateResponse(request, "public/seller_profile.html", await _ctx(
        request, db, seller=seller, listings=list(listings), reviews=list(reviews), shop_username=user.username))


@router.get("/sellers/{seller_id}", response_class=HTMLResponse)
async def seller_profile(request: Request, seller_id: int, db: AsyncSession = Depends(get_db)):
    from app.models import MarketplaceListing as _L
    from app.models import Review as _R
    seller = await db.get(Seller, seller_id)
    if not seller or not seller.is_active:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    listings = (await db.execute(select(_L).where(_L.seller_id == seller.id, _L.status == "active").order_by(_L.id.desc()).limit(24))).scalars().all()
    reviews = (await db.execute(select(_R).where(_R.seller_id == seller.id).order_by(_R.id.desc()).limit(20))).scalars().all()
    return templates.TemplateResponse(request, "public/seller_profile.html", await _ctx(
        request, db, seller=seller, listings=list(listings), reviews=list(reviews)))


@router.get("/donations", response_class=HTMLResponse)
async def donations_page(request: Request, db: AsyncSession = Depends(get_db)):
    profiles = (await db.execute(select(DonationProfile).where(DonationProfile.is_active.is_(True)).limit(50))).scalars().all()
    return templates.TemplateResponse(request, "public/donations.html", await _ctx(request, db, profiles=list(profiles)))


@router.get("/donations/{username}", response_class=HTMLResponse)
async def donation_profile(request: Request, username: str, db: AsyncSession = Depends(get_db)):
    profile = await donation_service.get_profile(db, username)
    if not profile:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    return templates.TemplateResponse(request, "public/donation_profile.html", await _ctx(request, db, profile=profile))


@router.get("/promotions", response_class=HTMLResponse)
async def promotions_page(request: Request, db: AsyncSession = Depends(get_db)):
    promos = (await db.execute(select(Promotion).where(Promotion.is_active.is_(True)).limit(50))).scalars().all()
    return templates.TemplateResponse(request, "public/promotions.html", await _ctx(request, db, promos=list(promos)))


@router.get("/support", response_class=HTMLResponse)
async def support_page(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "public/support.html", await _ctx(request, db))


@router.get("/support/{ticket_id}", response_class=HTMLResponse)
async def support_detail(request: Request, ticket_id: int, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "public/support_detail.html", await _ctx(request, db, ticket_id=ticket_id))


for _path, _tpl in [
    ("/about", "public/about.html"),
    ("/terms", "public/terms.html"),
    ("/privacy", "public/privacy.html"),
    ("/refund", "public/refund.html"),
    ("/auth/login", "auth/login.html"),
    ("/auth/register", "auth/register.html"),
    ("/login", "auth/login.html"),
    ("/register", "auth/register.html"),
    ("/forgot-password", "auth/login.html"),
    ("/reset-password", "auth/login.html"),
    ("/verify-email", "auth/verify.html"),
    ("/logout", "auth/logout.html"),
]:
    router.add_api_route(_path, _page(_tpl), response_class=HTMLResponse, methods=["GET"])


@router.get("/profile", response_class=HTMLResponse)
async def profile_alias() -> RedirectResponse:
    return RedirectResponse("/app/profile", status_code=302)


@router.get("/security", response_class=HTMLResponse)
async def security_alias() -> RedirectResponse:
    return RedirectResponse("/app/security", status_code=302)


@router.get("/orders", response_class=HTMLResponse)
async def orders_alias() -> RedirectResponse:
    return RedirectResponse("/app/orders", status_code=302)


# ---------- checkout ----------
@router.get("/checkout", response_class=HTMLResponse)
async def checkout_page(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "public/checkout.html", await _ctx(request, db))


# ---------- user dashboard ----------
for _path, _tpl in [
    ("/app", "app/dashboard.html"),
    ("/app/orders", "app/orders.html"),
    ("/app/wallet", "app/wallet.html"),
    ("/app/favorites", "app/favorites.html"),
    ("/app/notifications", "app/notifications.html"),
    ("/app/profile", "app/profile.html"),
    ("/app/security", "app/security.html"),
    ("/app/settings", "app/settings.html"),
    ("/app/seller", "app/seller.html"),
    ("/app/seller/orders", "app/seller_orders.html"),
    ("/app/seller/payouts", "app/seller_payouts.html"),
]:
    router.add_api_route(_path, _page(_tpl), response_class=HTMLResponse, methods=["GET"])


@router.get("/app/orders/{public_id}", response_class=HTMLResponse)
async def app_order_detail(request: Request, public_id: str, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "app/order_detail.html", await _ctx(request, db, public_id=public_id))


# ---------- admin panel (HTML shell; data via /api/admin/*) ----------
@router.get("/admin", response_class=HTMLResponse)
async def admin_index(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await _ctx(request, db)
    if not ctx["is_admin"]:
        return RedirectResponse("/auth/login", status_code=302)
    return templates.TemplateResponse(request, "admin/dashboard.html", ctx)


@router.get("/admin/{section}", response_class=HTMLResponse)
async def admin_section(request: Request, section: str, db: AsyncSession = Depends(get_db)):
    allowed = {"dashboard", "users", "games", "categories", "products", "pricing", "variants", "orders", "payments", "suppliers",
               "marketplace", "sellers", "donations", "promotions", "coupons", "payouts",
               "revenue", "wallets", "support", "fraud", "notifications", "telegram", "media", "audit", "settings"}
    if section not in allowed:
        return templates.TemplateResponse(request, "errors/404.html", await _ctx(request, db), status_code=404)
    ctx = await _ctx(request, db, section=section)
    if not ctx["is_admin"]:
        return RedirectResponse("/auth/login", status_code=302)
    tpl = f"admin/{section}.html"
    return templates.TemplateResponse(request, tpl, ctx)


# ---------- mini app ----------
@router.get("/miniapp", response_class=HTMLResponse)
async def miniapp(request: Request, db: AsyncSession = Depends(get_db)):
    return templates.TemplateResponse(request, "miniapp/index.html", await _ctx(request, db))
