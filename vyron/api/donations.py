"""Donations API — public page, create donation (amounts computed server-side),
creator's own page management."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok
from vyron.db.base import get_db
from vyron.db.models import DonationPage, User
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import get_current_user, get_optional_user
from vyron.security.sessions import client_ip
from vyron.services import donation_service, settings_service
from vyron.web.serializers import donation_page_public, donation_public, payment_public

router = APIRouter(prefix="/api/donations", tags=["donations"])


@router.get("/page/{username}")
def public_page(username: str, db: DbSession = Depends(get_db)):
    data = donation_service.get_public_page(db, username)
    fee_pct = settings_service.get_decimal_setting(db, "donation_fee_pct", "0")
    payload = donation_page_public(data)
    payload["platform_fee_pct"] = str(fee_pct)
    return ok(payload)


@router.post("")
def create_donation(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    donor: Optional[User] = Depends(get_optional_user),
):
    enforce_rate_limit(request, "donation", "5/minute", user_id=donor.id if donor else None)
    username = str(payload.get("username", "")).strip().lower()
    data = donation_service.get_public_page(db, username)
    page: DonationPage = data["page"]

    try:
        gross = Decimal(str(payload.get("amount", "")))
    except Exception:
        from vyron.errors import ValidationError

        raise ValidationError("Invalid amount.", code="AMOUNT_INVALID")

    donation, payment = donation_service.create_donation(
        db,
        page,
        gross_amount=gross,
        donor_user=donor,
        donor_name=str(payload.get("donor_name") or "")[:120],
        donor_email=str(payload.get("donor_email") or "")[:255],
        message=str(payload.get("message") or "")[:500],
        anonymous=bool(payload.get("anonymous", False)),
        provider_name=payload.get("provider"),
        idempotency_key=str(payload.get("idempotency_key") or "")[:80] or None,
        ip_address=client_ip(request),
    )
    fee_pct = settings_service.get_decimal_setting(db, "donation_fee_pct", "0")
    return ok(
        {
            "donation": donation_public(donation),
            "payment": payment_public(payment),
            "fee": {"pct": str(fee_pct), "amount": str(donation.platform_fee), "gross": str(donation.gross_amount)},
        },
        message_code="DONATION_CREATED",
    )


@router.get("/me/page")
def my_page(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    page = donation_service.ensure_page(db, user)
    stats = donation_service.user_donation_stats(db, user)
    return ok({"page": {"title": page.title, "description": page.description, "goal_amount": str(page.goal_amount) if page.goal_amount else None, "active": page.active, "url": f"/donate/{user.username}"}, "stats": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in stats.items()}})


@router.put("/me/page")
def update_my_page(
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    goal = payload.get("goal_amount")
    page = donation_service.update_page(
        db,
        user,
        title=payload.get("title"),
        description=payload.get("description"),
        goal_amount=Decimal(str(goal)) if goal not in (None, "") else None,
        active=payload.get("active"),
    )
    return ok({"title": page.title, "description": page.description, "goal_amount": str(page.goal_amount) if page.goal_amount else None, "active": page.active})


@router.get("/me/given")
def my_donations(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    from vyron.db.models import Donation

    donations = (
        db.query(Donation).filter(Donation.donor_user_id == user.id).order_by(Donation.created_at.desc()).limit(50).all()
    )
    return ok([donation_public(d) for d in donations])
