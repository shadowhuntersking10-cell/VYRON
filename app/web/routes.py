"""Public website routes (server-rendered Jinja2)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func

from app import models
from app.config import settings
from app.dependencies import Db

router = APIRouter()


def ctx(request: Request, **extra):
    templates = request.app.state.templates
    user = getattr(request.state, "user", None)
    lang = getattr(request.state, "lang", "uz")
    theme = "dark"
    if user and user.theme in ("dark", "light"):
        theme = user.theme
    elif request.cookies.get("vyron_theme") in ("dark", "light"):
        theme = request.cookies.get("vyron_theme")
    from app.dependencies import user_roles
    roles = user_roles(user) if user else set()
    base = {"request": request, "user": user, "lang": lang, "theme": theme,
            "is_admin": "admin" in roles, "is_seller": "seller" in roles or "admin" in roles,
            "settings": settings}
    base.update(extra)
    return base


def render(request: Request, name: str, **kw):
    return request.app.state.templates.TemplateResponse(request, name, ctx(request, **kw))


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Db):
    games = db.query(models.Game).filter_by(status="active").order_by(
        models.Game.featured.desc(), models.Game.sort_order).limit(12).all()
    products = db.query(models.Product).filter_by(status="active").order_by(
        models.Product.popular.desc(), models.Product.sales_count.desc()).limit(8).all()
    listings = db.query(models.MarketplaceListing).filter_by(status="active").order_by(
        models.MarketplaceListing.featured.desc()).limit(8).all()
    profiles = db.query(models.DonationProfile).filter_by(is_active=True).order_by(
        models.DonationProfile.raised_amount.desc()).limit(4).all()
    promos = db.query(models.Promotion).filter_by(is_active=True).order_by(models.Promotion.sort_order).limit(5).all()
    return render(request, "home.html", games=games, products=products, listings=listings,
                  profiles=profiles, promos=promos,
                  seo={"title": "VYRON — Gaming. Digital. Marketplace."})


@router.get("/games", response_class=HTMLResponse)
def games_page(request: Request, db: Db, search: str = ""):
    q = db.query(models.Game).filter_by(status="active")
    if search:
        q = q.filter(models.Game.name.ilike(f"%{search}%"))
    games = q.order_by(models.Game.sort_order).limit(100).all()
    cats = db.query(models.GameCategory).filter_by(is_active=True).all()
    return render(request, "games/list.html", games=games, cats=cats, search=search,
                  seo={"title": "Games — VYRON"})


@router.get("/games/{slug}", response_class=HTMLResponse)
def game_detail(slug: str, request: Request, db: Db, sort: str = "popular", search: str = ""):
    g = db.query(models.Game).filter_by(slug=slug, status="active").first()
    if not g:
        raise HTTPException(status_code=404)
    q = db.query(models.Product).filter_by(game_id=g.id, status="active")
    if search:
        q = q.filter(models.Product.name.ilike(f"%{search}%"))
    if sort == "price_asc":
        q = q.order_by(models.Product.customer_price)
    elif sort == "price_desc":
        q = q.order_by(models.Product.customer_price.desc())
    else:
        q = q.order_by(models.Product.popular.desc(), models.Product.sort_order)
    return render(request, "games/detail.html", game=g, products=q.all(), fields=g.fields,
                  sort=sort, search=search,
                  seo={"title": g.seo_title or f"{g.name} — VYRON", "description": g.seo_description or g.description})


@router.get("/products/{slug}", response_class=HTMLResponse)
def product_detail(slug: str, request: Request, db: Db):
    p = db.query(models.Product).filter(
        (models.Product.slug == slug) | (models.Product.id == slug) if slug.isdigit()
        else (models.Product.slug == slug)).first()
    if not p or p.status != "active":
        raise HTTPException(status_code=404)
    return render(request, "products/detail.html", product=p, game=p.game, variants=p.variants,
                  seo={"title": f"{p.name} — VYRON"})


@router.get("/marketplace", response_class=HTMLResponse)
def marketplace_page(request: Request, db: Db, category_id: int | None = None, search: str = ""):
    q = db.query(models.MarketplaceListing).filter_by(status="active")
    if category_id:
        q = q.filter_by(category_id=category_id)
    if search:
        q = q.filter(models.MarketplaceListing.title.ilike(f"%{search}%"))
    listings = q.order_by(models.MarketplaceListing.featured.desc()).limit(60).all()
    cats = db.query(models.MarketplaceCategory).filter_by(is_active=True).all()
    return render(request, "marketplace/list.html", listings=listings, cats=cats,
                  category_id=category_id, search=search, seo={"title": "Marketplace — VYRON"})


@router.get("/marketplace/{slug}", response_class=HTMLResponse)
def listing_page(slug: str, request: Request, db: Db):
    l = db.query(models.MarketplaceListing).filter(
        (models.MarketplaceListing.slug == slug) | (models.MarketplaceListing.id == slug) if slug.isdigit()
        else (models.MarketplaceListing.slug == slug)).first()
    if not l:
        raise HTTPException(status_code=404)
    seller = db.get(models.Seller, l.seller_id)
    reviews = db.query(models.Review).filter_by(listing_id=l.id).order_by(models.Review.id.desc()).limit(10).all()
    return render(request, "marketplace/detail.html", listing=l, seller=seller, reviews=reviews,
                  seo={"title": f"{l.title} — VYRON"})


@router.get("/seller/{username}", response_class=HTMLResponse)
def seller_page(username: str, request: Request, db: Db):
    s = db.query(models.Seller).filter_by(slug=username).first()
    if not s:
        raise HTTPException(status_code=404)
    listings = db.query(models.MarketplaceListing).filter_by(seller_id=s.id, status="active").limit(40).all()
    return render(request, "marketplace/seller.html", seller=s, listings=listings,
                  seo={"title": f"{s.shop_name} — VYRON"})


@router.get("/donations", response_class=HTMLResponse)
def donations_page(request: Request, db: Db):
    profiles = db.query(models.DonationProfile).filter_by(is_active=True).order_by(
        models.DonationProfile.raised_amount.desc()).limit(40).all()
    return render(request, "donations/list.html", profiles=profiles, seo={"title": "Donations — VYRON"})


@router.get("/donations/{username}", response_class=HTMLResponse)
def donation_profile(username: str, request: Request, db: Db):
    p = db.query(models.DonationProfile).filter_by(username=username, is_active=True).first()
    if not p:
        raise HTTPException(status_code=404)
    presets = db.query(models.DonationPreset).filter_by(is_active=True).order_by(models.DonationPreset.sort_order).all()
    recent = db.query(models.Donation).filter_by(profile_id=p.id, status="paid").order_by(
        models.Donation.id.desc()).limit(10).all()
    top = db.query(models.Donation).filter_by(profile_id=p.id, status="paid").order_by(
        models.Donation.amount.desc()).limit(5).all()
    goal = float(p.goal_amount or 0)
    progress = round(float(p.raised_amount or 0) / goal * 100, 1) if goal else 0
    return render(request, "donations/profile.html", profile=p, presets=presets,
                  recent=recent, top=top, progress=progress,
                  seo={"title": f"{p.display_name} — Donate — VYRON"})


@router.get("/promotions", response_class=HTMLResponse)
def promotions_page(request: Request, db: Db):
    promos = db.query(models.Promotion).filter_by(is_active=True).order_by(models.Promotion.sort_order).all()
    return render(request, "promotions.html", promos=promos, seo={"title": "Promotions — VYRON"})


@router.get("/support", response_class=HTMLResponse)
def support_page(request: Request, db: Db):
    return render(request, "support/list.html", seo={"title": "Support — VYRON"})


@router.get("/checkout", response_class=HTMLResponse)
def checkout_page(request: Request, db: Db, product: int | None = None, listing: int | None = None):
    p = db.get(models.Product, product) if product else None
    l = db.get(models.MarketplaceListing, listing) if listing else None
    game = p.game if p else None
    return render(request, "checkout/checkout.html", product=p, listing=l, game=game,
                  fields=game.fields if game else [], seo={"title": "Checkout — VYRON"})


@router.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request, db: Db):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login?next=/orders", status_code=302)
    orders = db.query(models.Order).filter_by(user_id=user.id).order_by(models.Order.id.desc()).limit(50).all()
    return render(request, "orders/list.html", orders=orders, seo={"title": "Orders — VYRON"})


@router.get("/orders/{public_id}", response_class=HTMLResponse)
def order_page(public_id: str, request: Request, db: Db):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login", status_code=302)
    o = db.query(models.Order).filter_by(public_id=public_id, user_id=user.id).first()
    if not o:
        raise HTTPException(status_code=404)
    try:
        timeline = json.loads(o.timeline or "[]")
    except Exception:
        timeline = []
    return render(request, "orders/detail.html", order=o, timeline=timeline,
                  seo={"title": f"Order {o.public_id} — VYRON"})


# ----- auth pages -----
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "auth/login.html", seo={"title": "Login — VYRON"})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "auth/register.html", seo={"title": "Register — VYRON"})


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_page(request: Request):
    return render(request, "auth/forgot.html", seo={"title": "Forgot password — VYRON"})


@router.get("/reset-password", response_class=HTMLResponse)
def reset_page(request: Request, token: str = ""):
    return render(request, "auth/reset.html", token=token, seo={"title": "Reset password — VYRON"})


@router.get("/verify-email", response_class=HTMLResponse)
def verify_page(request: Request, token: str = ""):
    return render(request, "auth/verify.html", token=token, seo={"title": "Verify email — VYRON"})


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Db):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login?next=/profile", status_code=302)
    from app.services import wallet as wallet_svc
    w = wallet_svc.get_or_create(db, user.id)
    db.commit()
    favs = db.query(models.Favorite).filter_by(user_id=user.id).all()
    notifs = db.query(models.Notification).filter_by(user_id=user.id).order_by(
        models.Notification.id.desc()).limit(10).all()
    seller = db.query(models.Seller).filter_by(user_id=user.id).first()
    return render(request, "profile/profile.html", wallet=w, favs=favs, notifs=notifs,
                  seller=seller, seo={"title": "Profile — VYRON"})


@router.get("/security", response_class=HTMLResponse)
def security_page(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse("/login?next=/security", status_code=302)
    return render(request, "profile/security.html", seo={"title": "Security — VYRON"})


@router.get("/logout")
def logout_page(request: Request):
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(settings.SESSION_COOKIE, path="/")
    resp.delete_cookie(settings.CSRF_COOKIE, path="/")
    return resp


# ----- legal / info -----
@router.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    return render(request, "info.html", page="about", seo={"title": "About — VYRON"})


@router.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return render(request, "info.html", page="terms", seo={"title": "Terms — VYRON"})


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return render(request, "info.html", page="privacy", seo={"title": "Privacy — VYRON"})


@router.get("/refund", response_class=HTMLResponse)
def refund_page(request: Request):
    return render(request, "info.html", page="refund", seo={"title": "Refund policy — VYRON"})


@router.get("/payment-info", response_class=HTMLResponse)
def payment_info_page(request: Request):
    return render(request, "info.html", page="payment_info", seo={"title": "Payments — VYRON"})


@router.get("/seller-terms", response_class=HTMLResponse)
def seller_terms_page(request: Request):
    return render(request, "info.html", page="seller_terms", seo={"title": "Seller terms — VYRON"})


@router.get("/donation-terms", response_class=HTMLResponse)
def donation_terms_page(request: Request):
    return render(request, "info.html", page="donation_terms", seo={"title": "Donation terms — VYRON"})


# ----- mini app + admin -----
@router.get("/tg-miniapp", response_class=HTMLResponse)
def miniapp_page(request: Request):
    return render(request, "miniapp.html", seo={"title": "VYRON Mini App"})


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    from app.dependencies import user_roles
    user = getattr(request.state, "user", None)
    if not user or "admin" not in user_roles(user):
        return RedirectResponse("/login?next=/admin", status_code=302)
    return render(request, "admin/index.html", seo={"title": "Admin — VYRON"})


@router.get("/healthz")
def healthz():
    return {"ok": True, "app": "VYRON"}
