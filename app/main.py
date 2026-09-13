from __future__ import annotations
import logging
from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager

from app.config import settings
from app.database import get_db, init_db, check_db_connection
from app.models.models import Game, Product, Promotion, DonationProfile, MarketplaceListing

# API routers
from app.api import auth as auth_api
from app.api import games as games_api
from app.api import products as products_api
from app.api import orders as orders_api
from app.api import payments as payments_api
from app.api import marketplace as marketplace_api
from app.api import donations as donations_api
from app.api import wallet as wallet_api
from app.api import users as users_api
from app.api import reviews as reviews_api
from app.api import favorites as favorites_api
from app.api import support as support_api
from app.api import notifications as notifications_api
from app.api import admin as admin_api

from app.dependencies import get_current_user_optional, get_current_user
from app.models.models import User

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="templates")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("VYRON starting up...")
    # Check DB
    connected = await check_db_connection()
    if not connected:
        logger.warning("Database connection failed, will try to create tables anyway")
    
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database init failed: {e}")

    # Seed if needed
    try:
        from app.seed import seed_all
        from app.database import AsyncSessionLocal
        # Only seed if tables empty
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select, func
            from app.models.models import Game
            result = await session.execute(select(func.count(Game.id)))
            count = result.scalar()
            if count == 0:
                logger.info("Seeding initial data...")
                await seed_all(session)
                logger.info("Seeding completed")
            else:
                logger.info(f"Found {count} games, skipping seed")
    except Exception as e:
        logger.warning(f"Seeding check failed: {e}", exc_info=True)

    logger.info("VYRON startup complete")
    yield
    # Shutdown
    logger.info("VYRON shutting down...")

def create_app() -> FastAPI:
    app = FastAPI(
        title="VYRON - Gaming Commerce Platform",
        description="Premium gaming marketplace, top-ups, donations, marketplace",
        version="1.0.0",
        lifespan=lifespan
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    try:
        app.mount("/static", StaticFiles(directory="static"), name="static")
    except Exception as e:
        logger.warning(f"Could not mount static: {e}")

    # API routes
    app.include_router(auth_api.router)
    app.include_router(games_api.router)
    app.include_router(products_api.router)
    app.include_router(orders_api.router)
    app.include_router(payments_api.router)
    app.include_router(marketplace_api.router)
    app.include_router(donations_api.router)
    app.include_router(wallet_api.router)
    app.include_router(users_api.router)
    app.include_router(reviews_api.router)
    app.include_router(favorites_api.router)
    app.include_router(support_api.router)
    app.include_router(notifications_api.router)
    app.include_router(admin_api.router)

    # Health
    @app.get("/health")
    async def health_check(db: AsyncSession = Depends(get_db)):
        from app.payments.providers import get_all_providers_status
        from app.suppliers.providers import get_supplier_status
        db_ok = await check_db_connection()
        return {
            "status": "ok" if db_ok else "degraded",
            "app": "VYRON",
            "version": "1.0.0",
            "database": "connected" if db_ok else "disconnected",
            "database_url": settings.effective_database_url.split("@")[-1] if "@" in settings.effective_database_url else settings.effective_database_url,
            "payments": get_all_providers_status(),
            "suppliers": get_supplier_status(),
            "sales_enabled": settings.SALES_ENABLED,
            "payments_enabled": settings.PAYMENTS_ENABLED,
            "supplier_orders_enabled": settings.SUPPLIER_ORDERS_ENABLED,
            "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN)
        }

    @app.get("/api/config")
    async def get_config():
        from app.payments.providers import get_all_providers_status
        return {
            "app_name": settings.APP_NAME,
            "app_url": settings.APP_URL,
            "payments": get_all_providers_status(),
            "sales_enabled": settings.SALES_ENABLED,
            "telegram_webapp_url": settings.TELEGRAM_WEBAPP_URL,
            "features": {
                "registration": settings.ENABLE_REGISTRATION,
                "marketplace": settings.ENABLE_MARKETPLACE,
                "donations": settings.ENABLE_DONATIONS,
                "wallet": settings.ENABLE_WALLET
            }
        }

    # Website routes (HTML)
    @app.get("/", response_class=HTMLResponse)
    async def home_page(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user_optional)):
        # Get featured games
        result = await db.execute(select(Game).where(Game.status == "ACTIVE", Game.featured == True).limit(8))
        featured_games = result.scalars().all()

        # Popular games
        result = await db.execute(select(Game).where(Game.status == "ACTIVE", Game.popular == True).limit(8))
        popular_games = result.scalars().all()
        if not popular_games:
            result = await db.execute(select(Game).where(Game.status == "ACTIVE").order_by(Game.sort_order).limit(8))
            popular_games = result.scalars().all()

        # Featured products
        result = await db.execute(select(Product).where(Product.is_active == True, Product.featured == True).limit(8))
        featured_products = result.scalars().all()

        # Popular products
        result = await db.execute(select(Product).where(Product.is_active == True, Product.popular == True).limit(8))
        popular_products = result.scalars().all()

        # Promotions
        result = await db.execute(select(Promotion).where(Promotion.is_active == True, Promotion.featured == True).limit(3))
        promotions = result.scalars().all()

        # Donation profiles
        result = await db.execute(select(DonationProfile).where(DonationProfile.is_active == True).order_by(DonationProfile.current_amount.desc()).limit(6))
        donation_profiles = result.scalars().all()

        # Marketplace featured
        result = await db.execute(select(MarketplaceListing).where(MarketplaceListing.status == "ACTIVE", MarketplaceListing.featured == True).limit(6))
        marketplace_featured = result.scalars().all()

        return templates.TemplateResponse(request, "home.html", {"current_user": current_user,
            "featured_games": featured_games,
            "popular_games": popular_games,
            "featured_products": featured_products,
            "popular_products": popular_products,
            "promotions": promotions,
            "donation_profiles": donation_profiles,
            "marketplace_featured": marketplace_featured,
            "settings": settings
        })

    @app.get("/games", response_class=HTMLResponse)
    async def games_page(request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user_optional)):
        result = await db.execute(select(Game).where(Game.status == "ACTIVE").order_by(Game.sort_order))
        games = result.scalars().all()
        return templates.TemplateResponse(request, "games/list.html", {"current_user": current_user,
            "games": games
        })

    @app.get("/games/{slug}", response_class=HTMLResponse)
    async def game_detail_page(slug: str, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user_optional)):
        result = await db.execute(select(Game).where(Game.slug == slug))
        game = result.scalar_one_or_none()
        if not game:
            return templates.TemplateResponse(request, "errors/404.html", {}, status_code=404)

        result = await db.execute(select(Product).where(Product.game_id == game.id, Product.is_active == True).order_by(Product.popular.desc(), Product.sort_order))
        products = result.scalars().all()

        return templates.TemplateResponse(request, "games/detail.html", {"current_user": current_user,
            "game": game,
            "products": products
        })

    @app.get("/products/{product_id}", response_class=HTMLResponse)
    async def product_detail_page(product_id: int, request: Request, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user_optional)):
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            return templates.TemplateResponse(request, "errors/404.html", {}, status_code=404)

        result = await db.execute(select(Game).where(Game.id == product.game_id))
        game = result.scalar_one_or_none()

        return templates.TemplateResponse(request, "products/detail.html", {"current_user": current_user,
            "product": product,
            "game": game
        })

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if current_user:
            return RedirectResponse(url="/", status_code=302)
        return templates.TemplateResponse(request, "auth/login.html", {})

    @app.get("/register", response_class=HTMLResponse)
    async def register_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if current_user:
            return RedirectResponse(url="/", status_code=302)
        return templates.TemplateResponse(request, "auth/register.html", {})

    @app.get("/profile", response_class=HTMLResponse)
    async def profile_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse(request, "profile/index.html", {"current_user": current_user})

    @app.get("/orders", response_class=HTMLResponse)
    async def orders_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if not current_user:
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse(request, "orders/list.html", {"current_user": current_user})

    @app.get("/checkout", response_class=HTMLResponse)
    async def checkout_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if not current_user:
            return RedirectResponse(url="/login?next=/checkout", status_code=302)
        return templates.TemplateResponse(request, "checkout/index.html", {"current_user": current_user})

    @app.get("/marketplace", response_class=HTMLResponse)
    async def marketplace_page(request: Request, current_user: User = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(MarketplaceListing).where(MarketplaceListing.status == "ACTIVE").order_by(MarketplaceListing.created_at.desc()).limit(20))
        listings = result.scalars().all()
        return templates.TemplateResponse(request, "marketplace/list.html", {"current_user": current_user, "listings": listings})

    @app.get("/marketplace/{listing_id}", response_class=HTMLResponse)
    async def marketplace_detail(listing_id: int, request: Request, current_user: User = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(MarketplaceListing).where(MarketplaceListing.id == listing_id))
        listing = result.scalar_one_or_none()
        if not listing:
            return templates.TemplateResponse(request, "errors/404.html", {}, status_code=404)
        return templates.TemplateResponse(request, "marketplace/detail.html", {"current_user": current_user, "listing": listing})

    @app.get("/donations", response_class=HTMLResponse)
    async def donations_page(request: Request, current_user: User = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(DonationProfile).where(DonationProfile.is_active == True).limit(20))
        profiles = result.scalars().all()
        return templates.TemplateResponse(request, "donations/list.html", {"current_user": current_user, "profiles": profiles})

    @app.get("/donations/{username}", response_class=HTMLResponse)
    async def donation_profile_page(username: str, request: Request, current_user: User = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(DonationProfile).where(DonationProfile.username == username))
        profile = result.scalar_one_or_none()
        if not profile:
            return templates.TemplateResponse(request, "errors/404.html", {}, status_code=404)
        return templates.TemplateResponse(request, "donations/profile.html", {"current_user": current_user, "profile": profile})

    @app.get("/support", response_class=HTMLResponse)
    async def support_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "support/index.html", {"current_user": current_user})

    @app.get("/about", response_class=HTMLResponse)
    async def about_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "legal/about.html", {"current_user": current_user})

    @app.get("/terms", response_class=HTMLResponse)
    async def terms_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "legal/terms.html", {"current_user": current_user})

    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "legal/privacy.html", {"current_user": current_user})

    @app.get("/refund", response_class=HTMLResponse)
    async def refund_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "legal/refund.html", {"current_user": current_user})

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        if not current_user or not current_user.is_admin:
            return RedirectResponse(url="/login", status_code=302)
        return templates.TemplateResponse(request, "admin/dashboard.html", {"current_user": current_user})

    @app.get("/admin/{path:path}", response_class=HTMLResponse)
    async def admin_subpages(path: str, request: Request, current_user: User = Depends(get_current_user_optional)):
        if not current_user or not current_user.is_admin:
            return RedirectResponse(url="/login", status_code=302)
        # Try to find template
        template_path = f"admin/{path}.html"
        try:
            return templates.TemplateResponse(request, template_path, {"current_user": current_user})
        except:
            return templates.TemplateResponse(request, "admin/dashboard.html", {"current_user": current_user})

    @app.get("/telegram-app", response_class=HTMLResponse)
    async def telegram_app_page(request: Request, current_user: User = Depends(get_current_user_optional)):
        return templates.TemplateResponse(request, "telegram/app.html", {"current_user": current_user})

    @app.get("/promotions", response_class=HTMLResponse)
    async def promotions_page(request: Request, current_user: User = Depends(get_current_user_optional), db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Promotion).where(Promotion.is_active == True).order_by(Promotion.sort_order))
        promos = result.scalars().all()
        return templates.TemplateResponse(request, "promotions/list.html", {"current_user": current_user, "promotions": promos})

    return app

# For backward compatibility with main.py importing
app = create_app()
