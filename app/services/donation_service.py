"""Donations: profiles, transparent fees, settlement."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Donation, DonationProfile, Order, RevenueLedger
from app.services import settings_service
from app.services.notification_service import notify_user
from app.utils.money import D, money_percent, money_sub, quantize_money


async def get_profile(db: AsyncSession, username: str) -> DonationProfile | None:
    return (await db.execute(select(DonationProfile).where(DonationProfile.username == username.lower()))).scalars().first()


async def get_or_create_profile(db: AsyncSession, user_id: int, username: str) -> DonationProfile:
    username = username.strip().lower()
    profile = (await db.execute(select(DonationProfile).where(DonationProfile.user_id == user_id))).scalars().first()
    if profile:
        return profile
    taken = await get_profile(db, username)
    if taken:
        raise ValueError("username_taken")
    profile = DonationProfile(user_id=user_id, username=username)
    db.add(profile)
    await db.flush()
    return profile


async def fee_percent(db: AsyncSession) -> float:
    return await settings_service.get_float(db, "donation_fee_percent")


async def settle_donation_order(db: AsyncSession, order: Order) -> None:
    await db.refresh(order, attribute_names=["items"])
    pct = D(await fee_percent(db))
    for item in order.items:
        if item.kind != "donation":
            continue
        profile_id = (item.meta or {}).get("profile_id")
        profile = await db.get(DonationProfile, profile_id) if profile_id else None
        if not profile:
            continue
        gross = D(item.total_price)
        fee = money_percent(gross, pct)
        net = money_sub(gross, fee)
        profile.current_amount = quantize_money(D(profile.current_amount) + net)
        donation = Donation(
            profile_id=profile.id, sender_id=order.user_id, order_id=order.id,
            amount=gross, platform_fee=fee, net_amount=net, currency=order.currency,
            message=(item.meta or {}).get("message"), is_anonymous=bool((item.meta or {}).get("anonymous")),
            status="paid",
        )
        db.add(donation)
        db.add(RevenueLedger(
            stream="donation_fee", order_id=order.id, gross=fee,
            supplier_cost=D(0), processing_fee=D(0), seller_payout=net,
            net=fee, currency=order.currency, meta={"profile_id": profile.id},
        ))
        await db.flush()
        await notify_user(db, user_id=profile.user_id, kind="donation", title="New donation 💙",
                          body=f"{'Someone' if donation.is_anonymous else 'A supporter'} donated {gross} {order.currency}.",
                          link=f"/donations/{profile.username}")
