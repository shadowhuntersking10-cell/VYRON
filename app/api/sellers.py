"""Seller dashboard APIs: earnings, orders, payouts."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_seller
from app.models import SellerPayout, User
from app.services import marketplace_service, payout_service

router = APIRouter(prefix="/api/seller", tags=["seller"])


class PayoutIn(BaseModel):
    amount: float
    method: str | None = None
    details: dict = {}


async def _seller(user: User, db: AsyncSession):
    seller = await marketplace_service.get_seller_for_user(db, user.id)
    if not seller:
        raise HTTPException(403, "seller_required")
    return seller


@router.get("/me")
async def seller_me(user: User = Depends(require_seller), db: AsyncSession = Depends(get_db)):
    seller = await _seller(user, db)
    bal = await marketplace_service.get_balance(db, seller.id)
    return {
        "seller": {"id": seller.id, "shop_name": seller.shop_name, "rating_avg": str(seller.rating_avg),
                   "sales_count": seller.sales_count, "is_verified": seller.is_verified},
        "balance": {"available": str(bal.available), "pending": str(bal.pending),
                    "lifetime_earned": str(bal.lifetime_earned), "currency": bal.currency},
    }


@router.get("/orders")
async def seller_orders(user: User = Depends(require_seller), db: AsyncSession = Depends(get_db)):
    """Orders that contain this seller's listings."""
    from app.models import MarketplaceListing, Order, OrderItem
    seller = await _seller(user, db)
    stmt = (
        select(Order, OrderItem, MarketplaceListing)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(MarketplaceListing, MarketplaceListing.id == OrderItem.listing_id)
        .where(OrderItem.kind == "marketplace", MarketplaceListing.seller_id == seller.id)
        .order_by(Order.id.desc())
        .limit(100)
    )
    rows = (await db.execute(stmt)).all()
    return [{
        "order_id": o.id, "public_id": o.public_id, "status": o.status.value,
        "title": i.title, "quantity": i.quantity, "total": str(i.total_price),
        "currency": o.currency, "created_at": o.created_at.isoformat(),
    } for o, i, _ in rows]


@router.get("/payouts")
async def payouts(user: User = Depends(require_seller), db: AsyncSession = Depends(get_db)):
    seller = await _seller(user, db)
    rows = (await db.execute(select(SellerPayout).where(SellerPayout.seller_id == seller.id).order_by(SellerPayout.id.desc()))).scalars().all()
    return [{"id": p.id, "amount": str(p.amount), "currency": p.currency, "status": p.status.value,
             "method": p.method, "created_at": p.created_at.isoformat()} for p in rows]


@router.post("/payouts")
async def request_payout(data: PayoutIn, user: User = Depends(require_seller), db: AsyncSession = Depends(get_db)):
    seller = await _seller(user, db)
    try:
        payout = await payout_service.request_payout(db, seller.id, data.amount, method=data.method, details=data.details)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"id": payout.id, "status": payout.status.value}
