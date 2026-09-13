"""Marketplace: sellers, listings, commission settlement (server-side)."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    MarketplaceListing, Order, RevenueLedger, Seller, SellerBalance, User, UserRole,
)
from app.services import settings_service
from app.services.notification_service import notify_user
from app.utils.money import D, money_percent, money_sub, quantize_money


async def get_seller_for_user(db: AsyncSession, user_id: int) -> Seller | None:
    return (await db.execute(select(Seller).where(Seller.user_id == user_id))).scalars().first()


async def become_seller(db: AsyncSession, user: User, shop_name: str, description: str | None = None) -> Seller:
    existing = await get_seller_for_user(db, user.id)
    if existing:
        return existing
    seller = Seller(user_id=user.id, shop_name=shop_name.strip(), description=(description or "").strip() or None)
    db.add(seller)
    await db.flush()
    db.add(SellerBalance(seller_id=seller.id))
    if user.role == UserRole.USER:
        user.role = UserRole.SELLER
    await db.flush()
    return seller


async def commission_for(db: AsyncSession, seller: Seller, category: str | None = None) -> Decimal:
    if seller.commission_percent is not None:
        return D(seller.commission_percent)
    if category:
        override = await settings_service.get_setting(db, f"commission_category_{category}")
        if override:
            try:
                return D(override)
            except Exception:
                pass
    return D(await settings_service.get_float(db, "marketplace_commission_percent"))


async def get_balance(db: AsyncSession, seller_id: int) -> SellerBalance:
    bal = (await db.execute(select(SellerBalance).where(SellerBalance.seller_id == seller_id))).scalars().first()
    if not bal:
        bal = SellerBalance(seller_id=seller_id)
        db.add(bal)
        await db.flush()
    return bal


async def settle_marketplace_order(db: AsyncSession, order: Order) -> None:
    """Credit sellers (minus commission), record commission in the ledger."""
    await db.refresh(order, attribute_names=["items"])
    for item in order.items:
        if item.kind != "marketplace" or not item.listing_id:
            continue
        listing = await db.get(MarketplaceListing, item.listing_id)
        if not listing:
            continue
        seller = await db.get(Seller, listing.seller_id)
        if not seller:
            continue
        pct = await commission_for(db, seller, listing.category)
        gross = D(item.total_price)
        commission = money_percent(gross, pct)
        seller_share = money_sub(gross, commission)
        bal = await get_balance(db, seller.id)
        bal.available = quantize_money(D(bal.available) + seller_share)
        bal.lifetime_earned = quantize_money(D(bal.lifetime_earned) + seller_share)
        seller.sales_count = (seller.sales_count or 0) + item.quantity
        if listing.stock != -1:
            listing.stock = max(0, listing.stock - item.quantity)
            if listing.stock == 0:
                listing.status = "sold"
        db.add(RevenueLedger(
            stream="marketplace_commission", order_id=order.id, gross=commission,
            supplier_cost=D(0), processing_fee=D(0),
            seller_payout=seller_share, net=commission, currency=order.currency,
            meta={"seller_id": seller.id, "listing_id": listing.id, "pct": float(pct)},
        ))
        await db.flush()
        await notify_user(db, user_id=seller.user_id, kind="seller", title="New sale 🎉",
                          body=f"{listing.title} × {item.quantity} — you earned {seller_share} {order.currency}.",
                          link="/app/seller/orders")
