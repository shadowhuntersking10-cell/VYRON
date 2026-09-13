"""Seller payouts: request -> admin review -> complete."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PayoutStatus, SellerBalance, SellerPayout
from app.services.audit_service import log_action
from app.services.notification_service import notify_user
from app.utils.money import D, money_sub, quantize_money


async def request_payout(db: AsyncSession, seller_id: int, amount, *, method: str | None, details: dict | None) -> SellerPayout:
    bal = (await db.execute(select(SellerBalance).where(SellerBalance.seller_id == seller_id))).scalars().first()
    if not bal or D(bal.available) < D(amount) or D(amount) <= 0:
        raise ValueError("insufficient_balance")
    bal.available = money_sub(bal.available, amount)
    bal.pending = quantize_money(D(bal.pending) + D(amount))
    payout = SellerPayout(seller_id=seller_id, amount=D(amount), currency=bal.currency,
                          status=PayoutStatus.REQUESTED, method=method, details=details or {})
    db.add(payout)
    await db.flush()
    return payout


async def set_status(
    db: AsyncSession, payout: SellerPayout, status: PayoutStatus,
    *, admin_id: int, note: str | None = None, seller_user_id: int | None = None,
) -> SellerPayout:
    payout.status = status
    payout.processed_by = admin_id
    payout.admin_note = (note or "")[:500] or None
    bal = (await db.execute(select(SellerBalance).where(SellerBalance.seller_id == payout.seller_id))).scalars().first()
    if bal and status in (PayoutStatus.FAILED, PayoutStatus.CANCELLED):
        # return funds to available
        bal.pending = money_sub(bal.pending, payout.amount)
        bal.available = quantize_money(D(bal.available) + D(payout.amount))
    elif bal and status == PayoutStatus.COMPLETED:
        bal.pending = money_sub(bal.pending, payout.amount)
    await log_action(db, action=f"payout_{status.value.lower()}", actor_id=admin_id,
                     entity="seller_payout", entity_id=payout.id, meta={"amount": str(payout.amount)})
    await db.flush()
    if seller_user_id:
        await notify_user(db, user_id=seller_user_id, kind="seller", title=f"Payout {status.value.lower()}",
                          body=f"Payout of {payout.amount} {payout.currency} is {status.value.lower()}.",
                          link="/app/seller/payouts")
    return payout
