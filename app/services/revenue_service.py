"""Revenue ledger: only verified (paid/completed) transactions are recorded."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, RevenueLedger
from app.utils.money import D, money_sub


async def record_order_revenue(db: AsyncSession, order: Order) -> RevenueLedger | None:
    """Create ledger entries for a completed order. Idempotent per order+stream."""
    if order.status != OrderStatus.COMPLETED:
        return None
    await db.refresh(order, attribute_names=["items"])
    kinds = {i.kind for i in order.items}
    stream = "topup_markup"
    if kinds == {"marketplace"}:
        stream = "marketplace_commission"
    elif kinds == {"donation"}:
        stream = "donation_fee"

    existing = (
        await db.execute(
            select(RevenueLedger).where(RevenueLedger.order_id == order.id, RevenueLedger.stream == stream)
        )
    ).scalars().first()
    if existing:
        return existing

    from app.services import settings_service as _ss
    from app.utils.money import money_percent as _pct

    supplier_cost = sum((D(i.supplier_cost) for i in order.items), D(0))
    gross = D(order.total)
    fee_pct = D(await _ss.get_float(db, "payment_fee_percent"))
    processing_fee = _pct(gross, fee_pct)
    net = money_sub(money_sub(money_sub(gross, supplier_cost), D(order.discount)), processing_fee)
    entry = RevenueLedger(
        stream=stream, order_id=order.id, gross=gross,
        supplier_cost=supplier_cost, processing_fee=processing_fee,
        seller_payout=D(0), net=net, currency=order.currency,
    )
    db.add(entry)
    if D(order.service_fee) > 0:
        db.add(RevenueLedger(
            stream="service_fee", order_id=order.id, gross=D(order.service_fee),
            supplier_cost=D(0), processing_fee=D(0), seller_payout=D(0),
            net=D(order.service_fee), currency=order.currency,
        ))
    await db.flush()
    return entry


async def revenue_summary(db: AsyncSession, *, since: dt.datetime | None = None) -> dict:
    stmt = select(
        RevenueLedger.stream,
        func.coalesce(func.sum(RevenueLedger.gross), 0),
        func.coalesce(func.sum(RevenueLedger.supplier_cost), 0),
        func.coalesce(func.sum(RevenueLedger.net), 0),
        func.count(RevenueLedger.id),
    ).group_by(RevenueLedger.stream)
    if since:
        stmt = stmt.where(RevenueLedger.created_at >= since)
    rows = (await db.execute(stmt)).all()
    return {
        "by_stream": [
            {"stream": s, "gross": float(g), "supplier_cost": float(c), "net": float(n), "count": cnt}
            for s, g, c, n, cnt in rows
        ],
        "total_gross": float(sum(D(r[1]) for r in rows)),
        "total_net": float(sum(D(r[3]) for r in rows)),
    }
