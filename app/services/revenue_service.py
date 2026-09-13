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


async def revenue_summary(
    db: AsyncSession,
    *,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> dict:
    stmt = select(
        RevenueLedger.stream,
        func.coalesce(func.sum(RevenueLedger.gross), 0),
        func.coalesce(func.sum(RevenueLedger.supplier_cost), 0),
        func.coalesce(func.sum(RevenueLedger.net), 0),
        func.count(RevenueLedger.id),
    ).group_by(RevenueLedger.stream)
    if since:
        stmt = stmt.where(RevenueLedger.created_at >= since)
    if until:
        stmt = stmt.where(RevenueLedger.created_at <= until)
    rows = (await db.execute(stmt)).all()
    return {
        "by_stream": [
            {"stream": s, "gross": float(g), "supplier_cost": float(c), "net": float(n), "count": cnt}
            for s, g, c, n, cnt in rows
        ],
        "total_gross": float(sum(D(r[1]) for r in rows)),
        "total_net": float(sum(D(r[3]) for r in rows)),
    }


def resolve_range(value: str, *, days: int = 30,
                  start: dt.datetime | None = None,
                  end: dt.datetime | None = None) -> tuple[dt.datetime | None, dt.datetime | None]:
    """Named ranges: today / 7d / 30d / custom / all."""
    now = dt.datetime.now(dt.timezone.utc)
    value = (value or "30d").lower()
    if value == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), None
    if value == "7d":
        return now - dt.timedelta(days=7), None
    if value == "custom":
        return start, end
    if value == "all":
        return None, None
    return now - dt.timedelta(days=days), None


async def revenue_tops(db: AsyncSession, *, since: dt.datetime | None = None,
                       until: dt.datetime | None = None, limit: int = 10) -> dict:
    """Top games / products / sellers by completed-order revenue."""
    from app.models import Game, MarketplaceListing, OrderItem, Product, Seller

    item_stmt = (select(OrderItem).join(Order, Order.id == OrderItem.order_id)
                 .where(Order.status == OrderStatus.COMPLETED))
    if since:
        item_stmt = item_stmt.where(Order.completed_at >= since)
    if until:
        item_stmt = item_stmt.where(Order.completed_at <= until)
    items = (await db.execute(item_stmt)).scalars().all()

    product_ids = {it.product_id for it in items if it.product_id}
    listing_ids = {it.listing_id for it in items if it.listing_id}
    products = {}
    if product_ids:
        rows = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
        products = {p.id: p for p in rows}
    listings = {}
    if listing_ids:
        rows = (await db.execute(select(MarketplaceListing).where(MarketplaceListing.id.in_(listing_ids)))).scalars().all()
        listings = {li.id: li for li in rows}

    game_totals: dict[int, dict] = {}
    product_totals: dict[str, dict] = {}
    seller_totals: dict[int, dict] = {}
    for it in items:
        gross = D(it.unit_price) * (it.quantity or 1)
        prod = products.get(it.product_id) if it.product_id else None
        if prod and prod.game_id:
            g = game_totals.setdefault(prod.game_id, {"gross": D(0), "orders": 0})
            g["gross"] += gross
            g["orders"] += 1
        key = it.title or f"product:{it.product_id}"
        p = product_totals.setdefault(key, {"gross": D(0), "orders": 0})
        p["gross"] += gross
        p["orders"] += 1
        listing = listings.get(it.listing_id) if it.listing_id else None
        if listing:
            s = seller_totals.setdefault(listing.seller_id, {"gross": D(0), "orders": 0})
            s["gross"] += gross
            s["orders"] += 1

    game_names = {}
    if game_totals:
        games = (await db.execute(select(Game).where(Game.id.in_(list(game_totals))))).scalars().all()
        game_names = {g.id: g.title for g in games}
    seller_names = {}
    seller_ids = [s for s in seller_totals if s]
    if seller_ids:
        sellers = (await db.execute(select(Seller).where(Seller.id.in_(seller_ids)))).scalars().all()
        seller_names = {s.id: s.shop_name for s in sellers}

    def _top(mapping: dict, names: dict | None = None) -> list[dict]:
        ranked = sorted(mapping.items(), key=lambda kv: kv[1]["gross"], reverse=True)[:limit]
        return [{"id": k, "name": (names or {}).get(k, str(k)),
                 "gross": float(v["gross"]), "orders": v["orders"]} for k, v in ranked]

    return {
        "top_games": _top(game_totals, game_names),
        "top_products": [{"name": k, "gross": float(v["gross"]), "orders": v["orders"]}
                         for k, v in sorted(product_totals.items(),
                                            key=lambda kv: kv[1]["gross"], reverse=True)[:limit]],
        "top_sellers": _top(seller_totals, seller_names),
    }
