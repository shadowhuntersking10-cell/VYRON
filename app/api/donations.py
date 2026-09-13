from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models import Donation, DonationProfile, Order, OrderItem, OrderStatus, User
from app.services import donation_service
from app.utils.helpers import generate_public_id, utcnow
from app.utils.money import D

router = APIRouter(prefix="/api/donations", tags=["donations"])


class ProfileIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    bio: str | None = None
    goal_title: str | None = None
    goal_amount: float = 0


class DonateIn(BaseModel):
    amount: float = Field(gt=0)
    message: str | None = Field(default=None, max_length=500)
    anonymous: bool = False
    provider: str = "payme"


@router.get("/profiles")
async def profiles(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(DonationProfile).where(DonationProfile.is_active.is_(True)).limit(50))).scalars().all()
    return [{"username": p.username, "bio": p.bio, "avatar_url": p.avatar_url,
             "goal_title": p.goal_title, "goal_amount": str(p.goal_amount),
             "current_amount": str(p.current_amount), "currency": p.currency} for p in rows]


@router.get("/profiles/{username}")
async def profile_detail(username: str, db: AsyncSession = Depends(get_db)):
    p = await donation_service.get_profile(db, username)
    if not p:
        raise HTTPException(404, "profile_not_found")
    recent = (await db.execute(select(Donation).where(Donation.profile_id == p.id, Donation.status == "paid")
                               .order_by(Donation.id.desc()).limit(10))).scalars().all()
    top = (await db.execute(select(Donation).where(Donation.profile_id == p.id, Donation.status == "paid")
                            .order_by(Donation.amount.desc()).limit(5))).scalars().all()
    fee_pct = await donation_service.fee_percent(db)
    from app.services import settings_service
    presets = await settings_service.donation_presets_for(db, p.currency)
    return {
        "username": p.username, "bio": p.bio, "avatar_url": p.avatar_url,
        "goal_title": p.goal_title, "goal_amount": str(p.goal_amount),
        "current_amount": str(p.current_amount), "currency": p.currency,
        "fee_percent": fee_pct, "presets": presets,
        "recent": [{"amount": str(d.amount), "message": d.message, "anonymous": d.is_anonymous,
                    "created_at": d.created_at.isoformat()} for d in recent],
        "top": [{"amount": str(d.amount), "anonymous": d.is_anonymous} for d in top],
    }


@router.post("/profiles")
async def create_profile(data: ProfileIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        p = await donation_service.get_or_create_profile(db, user.id, data.username)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    p.bio = data.bio
    p.goal_title = data.goal_title
    p.goal_amount = D(data.goal_amount)
    await db.commit()
    return {"username": p.username}


@router.post("/profiles/{username}/donate")
async def donate(username: str, data: DonateIn, db: AsyncSession = Depends(get_db),
                 user: User | None = Depends(get_current_user_optional)):
    p = await donation_service.get_profile(db, username)
    if not p:
        raise HTTPException(404, "profile_not_found")
    order = Order(
        public_id=generate_public_id(), user_id=user.id if user else None,
        status=OrderStatus.PENDING_PAYMENT, idempotency_key=generate_public_id("don"),
        subtotal=D(data.amount), discount=D(0), service_fee=D(0), platform_fee=D(0),
        total=D(data.amount), currency=p.currency,
        timeline=[{"event": "order_created", "at": utcnow().isoformat()}],
    )
    db.add(order)
    await db.flush()
    db.add(OrderItem(order_id=order.id, kind="donation", title=f"Donation to @{p.username}",
                     quantity=1, unit_price=D(data.amount), total_price=D(data.amount),
                     meta={"profile_id": p.id, "message": data.message, "anonymous": data.anonymous}))
    await db.commit()

    from app.payments.base import ProviderNotConfigured
    from app.payments.manager import get_payment_manager

    manager = get_payment_manager()
    try:
        payment = await manager.init_payment(db, order, data.provider)
        await db.commit()
    except ProviderNotConfigured:
        return {"order_id": order.public_id, "payment": None, "error": "payment_provider_not_configured",
                "providers": manager.status_list()}
    return {"order_id": order.public_id,
            "payment": {"id": payment.id, "provider": payment.provider, "checkout_url": payment.checkout_url,
                        "status": payment.status.value}}
