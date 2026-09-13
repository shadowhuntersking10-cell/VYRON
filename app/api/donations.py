"""Donations API: profiles, presets, donate flow."""
from __future__ import annotations

import json
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app import models
from app.config import settings
from app.dependencies import Db, require_user
from app.donations import fee_breakdown
from app.payments.service import PaymentError, PaymentService
from app.schemas import DonateIn
from app.services import orders as order_svc
from app.services.pricing import q
from app.utils.security import new_token

router = APIRouter(prefix="/api/donations", tags=["donations"])


@router.get("/presets")
def presets(db: Db):
    items = db.query(models.DonationPreset).filter_by(is_active=True).order_by(models.DonationPreset.sort_order).all()
    return {"items": [{"id": p.id, "amount": str(p.amount), "currency": p.currency} for p in items]}


@router.get("/profiles")
def profiles(db: Db, page: int = 1, per_page: int = 24):
    query = db.query(models.DonationProfile).filter_by(is_active=True).order_by(models.DonationProfile.raised_amount.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return {"items": [{"username": p.username, "display_name": p.display_name, "bio": p.bio,
                       "avatar": p.avatar, "cover": p.cover, "goal": str(p.goal_amount),
                       "raised": str(p.raised_amount)} for p in items], "total": total}


@router.get("/profiles/{username}")
def profile_detail(username: str, db: Db):
    p = db.query(models.DonationProfile).filter_by(username=username, is_active=True).first()
    if not p:
        raise HTTPException(status_code=404, detail="profile_not_found")
    recent = db.query(models.Donation).filter_by(profile_id=p.id, status="paid").order_by(
        models.Donation.id.desc()).limit(10).all()
    top = db.query(models.Donation).filter_by(profile_id=p.id, status="paid").order_by(
        models.Donation.amount.desc()).limit(5).all()

    def _d(d):
        return {"amount": str(d.amount), "message": d.message,
                "name": "Anonymous" if d.is_anonymous else (d.donor_name or "Supporter"),
                "created_at": d.created_at.isoformat()}

    goal = q(p.goal_amount)
    progress = float((q(p.raised_amount) / goal * 100).quantize(Decimal("0.1"))) if goal > 0 else 0
    return {"username": p.username, "display_name": p.display_name, "bio": p.bio,
            "avatar": p.avatar, "cover": p.cover, "goal": str(p.goal_amount),
            "raised": str(p.raised_amount), "progress": progress,
            "recent": [_d(d) for d in recent], "top": [_d(d) for d in top],
            "fee_percent": str(settings.DONATION_FEE_PERCENT)}


@router.post("/profiles/{username}/donate")
def donate(username: str, body: DonateIn, request: Request, db: Db):
    user = require_user(request, db)
    if not settings.SALES_ENABLED:
        raise HTTPException(status_code=403, detail="sales_disabled")
    p = db.query(models.DonationProfile).filter_by(username=username, is_active=True).first()
    if not p:
        raise HTTPException(status_code=404, detail="profile_not_found")
    amount = q(body.amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="invalid_amount")
    bd = fee_breakdown(amount, settings.DONATION_FEE_PERCENT)
    order = models.Order(public_id=order_svc.public_id(), user_id=user.id, kind="donation",
                         status="PENDING_PAYMENT", currency=settings.DEFAULT_CURRENCY,
                         subtotal=amount, total=amount, idempotency_key=new_token(24))
    db.add(order)
    db.flush()
    db.add(models.OrderItem(order_id=order.id, title=f"Donation to {p.display_name}",
                            quantity=1, unit_price=amount, total_price=amount))
    donation = models.Donation(profile_id=p.id, donor_id=user.id, order_id=order.id,
                               amount=amount, platform_fee=bd["fee"], net_amount=bd["net"],
                               message=body.message[:500], is_anonymous=body.is_anonymous,
                               donor_name=(body.donor_name or user.display_name or user.username)[:128],
                               status="pending")
    db.add(donation)
    db.flush()
    order_svc.push_timeline(order, "CREATED", f"donation to {p.username}")
    db.commit()
    try:
        payment, action = PaymentService(db).create_for_order(
            order, body.provider, return_url=f"{settings.BASE_URL}/donations/{p.username}")
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=e.key)
    return {"order": order.public_id, "breakdown": {k: str(v) for k, v in bd.items()},
            "payment": {"id": payment.id, "status": payment.status}, "action": action}


class ProfileUpsert(BaseModel):
    display_name: str
    bio: str = ""
    goal_amount: float = 0


@router.post("/profiles/me")
def upsert_my_profile(body: ProfileUpsert, request: Request, db: Db):
    user = require_user(request, db)
    p = db.query(models.DonationProfile).filter_by(user_id=user.id).first()
    if not p:
        p = models.DonationProfile(user_id=user.id, username=user.username,
                                   display_name=body.display_name[:128])
        db.add(p)
    p.display_name = body.display_name[:128]
    p.bio = body.bio[:2000]
    p.goal_amount = q(body.goal_amount)
    db.commit()
    return {"ok": True, "username": p.username}
