from __future__ import annotations
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.models import DonationProfile, DonationPreset, Donation, User
from app.dependencies import get_current_user_optional, get_current_user
from typing import Optional
from decimal import Decimal
from app.utils.security import generate_idempotency_key
from app.services.pricing import PricingService

router = APIRouter(prefix="/api/donations", tags=["donations"])

@router.get("/presets")
async def list_presets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DonationPreset).where(DonationPreset.is_active == True).order_by(DonationPreset.sort_order))
    presets = result.scalars().all()
    return [{"id": p.id, "amount": float(p.amount), "currency": p.currency, "label": p.label} for p in presets]

@router.get("/profiles")
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100)
):
    query = select(DonationProfile).where(DonationProfile.is_active == True)
    if search:
        query = query.where(DonationProfile.display_name.ilike(f"%{search}%") | DonationProfile.username.ilike(f"%{search}%"))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.order_by(DonationProfile.current_amount.desc()).offset((page-1)*per_page).limit(per_page)
    result = await db.execute(query)
    profiles = result.scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "username": p.username,
                "display_name": p.display_name,
                "bio": p.bio,
                "avatar_url": p.avatar_url,
                "cover_url": p.cover_url,
                "goal_amount": float(p.goal_amount) if p.goal_amount else None,
                "current_amount": float(p.current_amount),
                "total_donations": p.total_donations,
                "progress": float(p.current_amount / p.goal_amount * 100) if p.goal_amount and p.goal_amount > 0 else None
            } for p in profiles
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page -1)//per_page if total else 1
    }

@router.get("/profiles/{username}")
async def get_profile(username: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DonationProfile).where(DonationProfile.username == username))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Donation profile not found")

    # Get recent donations
    recent_result = await db.execute(
        select(Donation).where(Donation.recipient_id == profile.id, Donation.payment_status == "PAID").order_by(Donation.created_at.desc()).limit(10)
    )
    recent = recent_result.scalars().all()

    # Top donors
    top_result = await db.execute(
        select(Donation.donor_name, func.sum(Donation.amount).label("total"))
        .where(Donation.recipient_id == profile.id, Donation.payment_status == "PAID")
        .group_by(Donation.donor_name)
        .order_by(func.sum(Donation.amount).desc())
        .limit(10)
    )
    top = top_result.all()

    return {
        "id": profile.id,
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "cover_url": profile.cover_url,
        "goal_amount": float(profile.goal_amount) if profile.goal_amount else None,
        "current_amount": float(profile.current_amount),
        "total_donations": profile.total_donations,
        "progress": float(profile.current_amount / profile.goal_amount * 100) if profile.goal_amount and profile.goal_amount > 0 else None,
        "recent_donations": [
            {
                "id": d.id,
                "amount": float(d.amount),
                "message": d.message if not d.is_anonymous else None,
                "donor_name": "Anonymous" if d.is_anonymous else (d.donor_name or "Supporter"),
                "created_at": d.created_at.isoformat()
            } for d in recent
        ],
        "top_supporters": [{"name": row[0] or "Anonymous", "total": float(row[1])} for row in top]
    }

@router.post("/donate/{username}")
async def donate(
    username: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_optional)
):
    amount = payload.get("amount")
    message = payload.get("message")
    is_anonymous = payload.get("is_anonymous", False)
    donor_name = payload.get("donor_name")

    if not amount or float(amount) <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")

    result = await db.execute(select(DonationProfile).where(DonationProfile.username == username))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    amount_dec = Decimal(str(amount))
    fee_calc = PricingService.calculate_donation_fees(amount_dec)

    donation = Donation(
        recipient_id=profile.id,
        donor_id=current_user.id if current_user else None,
        amount=fee_calc["gross"],
        currency="UZS",
        platform_fee=fee_calc["fee"],
        net_amount=fee_calc["net"],
        message=message,
        is_anonymous=is_anonymous,
        payment_status="CREATED",
        donor_name=donor_name or (current_user.display_name if current_user else "Guest"),
        idempotency_key=generate_idempotency_key()
    )
    db.add(donation)
    await db.flush()

    # For now, mark as paid if wallet or manual? Actually need payment flow
    # We'll return donation with payment instructions
    await db.commit()

    return {
        "success": True,
        "donation": {
            "id": donation.id,
            "amount": float(donation.amount),
            "fee": float(donation.platform_fee),
            "net": float(donation.net_amount),
            "recipient": profile.display_name
        },
        "payment_required": True,
        "message": "Donation created, proceed to payment"
    }
