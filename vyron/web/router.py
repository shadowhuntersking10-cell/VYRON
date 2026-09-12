"""SSR website routes — public pages, auth pages, dashboard, seller area,
admin panel shell and the Telegram Mini App page.

Auth guards are SERVER-SIDE: pages read the session cookie; role checks use
the same RBAC helpers as the API. No client-side flags are trusted.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import get_db
from vyron.db.models import User
from vyron.enums import STAFF_ROLES, UserRole
from vyron.errors import NotFoundError
from vyron.security.rbac import get_optional_user
from vyron.web.templates import render

router = APIRouter(include_in_schema=False)


# --- public --------------------------------------------------------------------------------
@router.get("/")
def home(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    data = home_service.home_payload(db)
    return render(request, "home.html", user, **data)


@router.get("/games")
def games_page(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    return render(request, "games.html", user, games=home_service.all_games(db))


@router.get("/games/{slug}")
def game_page(slug: str, request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    data = home_service.game_detail(db, slug)
    return render(request, "game_detail.html", user, **data)


@router.get("/products")
def products_page(
    request: Request,
    db: DbSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    game: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    from vyron.services import home_service

    data = home_service.products_page(db, game_slug=game, query=q)
    return render(request, "products.html", user, **data)


@router.get("/products/{slug}")
def product_page(slug: str, request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    data = home_service.product_detail(db, slug)
    return render(request, "product_detail.html", user, **data)


@router.get("/marketplace")
def marketplace_page(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    return render(request, "marketplace.html", user, **home_service.marketplace_page(db))


@router.get("/marketplace/listing/{listing_id}")
def listing_page(listing_id: str, request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    return render(request, "listing_detail.html", user, **home_service.listing_detail(db, listing_id))


@router.get("/sellers/{username}")
def seller_page(username: str, request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    return render(request, "seller_profile.html", user, **home_service.seller_profile_page(db, username))


@router.get("/promotions")
def promotions_page(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import home_service

    return render(request, "promotions.html", user, **home_service.promotions_page(db))


@router.get("/donations")
def donations_index_page(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user), q: Optional[str] = Query(None)):
    from vyron.services import home_service

    return render(request, "donations_index.html", user, creators=home_service.donations_index(db, q), query=q or "")


@router.get("/donate/{username}")
def donate_page(username: str, request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    from vyron.services import donation_service, settings_service

    data = donation_service.get_public_page(db, username)
    return render(
        request, "donate.html", user,
        page_data=data,
        fee_pct=settings_service.get_decimal_setting(db, "donation_fee_pct", "0"),
        fee_fixed=settings_service.get_decimal_setting(db, "donation_fee_fixed", "0"),
    )


@router.get("/support")
def support_page(request: Request, db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    tickets = []
    if user is not None:
        from vyron.services import support_service

        tickets = support_service.list_tickets(db, user=user, page=1, page_size=20)["items"]
    return render(request, "support.html", user, tickets=tickets)


@router.get("/about")
def about_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    return render(request, "about.html", user)


@router.get("/terms")
def terms_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    return render(request, "legal.html", user, legal_doc="terms")


@router.get("/privacy")
def privacy_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    return render(request, "legal.html", user, legal_doc="privacy")


@router.get("/refund-policy")
def refund_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    return render(request, "legal.html", user, legal_doc="refund")


@router.get("/search")
def search_page(request: Request, user: Optional[User] = Depends(get_optional_user), q: str = Query("")):
    return render(request, "search.html", user, query=q)


# --- auth pages ------------------------------------------------------------------------------
@router.get("/login")
def login_page(request: Request, user: Optional[User] = Depends(get_optional_user), next: str = Query("/dashboard")):
    if user is not None:
        return RedirectResponse(next or "/dashboard", status_code=302)
    return render(request, "login.html", user, next_url=next)


@router.get("/register")
def register_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "register.html", user)


@router.get("/forgot-password")
def forgot_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    return render(request, "forgot_password.html", user)


@router.get("/reset-password")
def reset_page(request: Request, user: Optional[User] = Depends(get_optional_user), token: str = Query("")):
    return render(request, "reset_password.html", user, reset_token=token)


@router.get("/verify-email")
def verify_page(request: Request, user: Optional[User] = Depends(get_optional_user), token: str = Query("")):
    return render(request, "verify_email.html", user, verify_token=token)


# --- authenticated pages -------------------------------------------------------------------------
@router.get("/checkout")
def checkout_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    if user is None:
        return RedirectResponse("/login?next=/checkout", status_code=302)
    return render(request, "checkout.html", user)


@router.get("/dashboard")
@router.get("/dashboard/{section}")
def dashboard_page(request: Request, section: str = "overview", user: Optional[User] = Depends(get_optional_user)):
    if user is None:
        return RedirectResponse("/login?next=/dashboard", status_code=302)
    return render(request, "dashboard.html", user, section=section)


@router.get("/seller")
@router.get("/seller/{section}")
def seller_page_area(request: Request, section: str = "overview", db: DbSession = Depends(get_db), user: Optional[User] = Depends(get_optional_user)):
    if user is None:
        return RedirectResponse("/login?next=/seller", status_code=302)
    if UserRole(user.role) not in {UserRole.SELLER, UserRole.ADMIN, UserRole.SUPER_ADMIN}:
        return render(request, "seller_apply.html", user)
    return render(request, "seller.html", user, section=section)


@router.get("/admin")
@router.get("/admin/{section}")
def admin_page(request: Request, section: str = "dashboard", user: Optional[User] = Depends(get_optional_user)):
    if user is None:
        return RedirectResponse("/login?next=/admin", status_code=302)
    # Server-side gate: only staff roles ever receive the admin shell.
    if UserRole(user.role) not in STAFF_ROLES:
        raise NotFoundError("Page not found.")
    return render(request, "admin.html", user, section=section)


# --- Telegram Mini App -------------------------------------------------------------------------
@router.get("/miniapp")
def miniapp_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    from vyron.config import settings

    return render(request, "miniapp.html", user, telegram_enabled=settings.telegram_configured)
