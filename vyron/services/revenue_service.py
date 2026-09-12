"""Revenue ledger service — immutable, server-side financial accounting.

Every entry is append-only with a unique idempotency key, so no business event
can ever be double-counted (crash-safe under retries). Only verified payments
and completed business events reach this ledger — never unpaid orders.

Streams:
  GROSS_REVENUE        money received from customers (verified payments)
  SUPPLIER_COST        money paid to suppliers (successful deliveries)
  TOPUP_MARGIN         selling price - supplier cost (per completed item)
  MARKETPLACE_COMMISSION / DONATION_FEE / SERVICE_FEE / PROMOTION_FEE /
  SUBSCRIPTION_FEE     platform revenue streams
  PAYMENT_FEE          processing fees charged by providers
  REFUND / SELLER_PAYOUT outflows
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from vyron.db.models import Order, RevenueLedgerEntry
from vyron.enums import RevenueStream
from vyron.logging import get_logger
from vyron.money import ZERO, sum_money, to_money

log = get_logger("vyron.revenue")


def record_entry(
    db: DbSession,
    stream: RevenueStream | str,
    amount: Decimal,
    idempotency_key: str,
    *,
    currency: str = "USD",
    order_id: Optional[str] = None,
    payment_id: Optional[str] = None,
    donation_id: Optional[str] = None,
    seller_order_id: Optional[str] = None,
    payout_id: Optional[str] = None,
    product_id: Optional[str] = None,
    game_id: Optional[str] = None,
    description: Optional[str] = None,
    commit: bool = False,
) -> Optional[RevenueLedgerEntry]:
    amount = to_money(amount)
    if amount == ZERO:
        return None
    entry = RevenueLedgerEntry(
        stream=stream.value if isinstance(stream, RevenueStream) else str(stream),
        amount=amount,
        currency=currency,
        order_id=order_id,
        payment_id=payment_id,
        donation_id=donation_id,
        seller_order_id=seller_order_id,
        payout_id=payout_id,
        product_id=product_id,
        game_id=game_id,
        idempotency_key=idempotency_key,
        description=(description or "")[:300] or None,
    )
    db.add(entry)
    try:
        if commit:
            db.commit()
        else:
            db.flush()
        return entry
    except IntegrityError:
        db.rollback()
        log.info("revenue entry already recorded (idempotent skip)", key=idempotency_key)
        return None


# --- business-event helpers -----------------------------------------------------------
def record_verified_payment(db: DbSession, payment, *, service_fee_amount: Decimal = ZERO, order: Optional[Order] = None, product_id: Optional[str] = None, game_id: Optional[str] = None, donation_id: Optional[str] = None, seller_order_id: Optional[str] = None) -> None:
    record_entry(
        db, RevenueStream.GROSS_REVENUE, payment.amount, f"gross:payment:{payment.id}",
        currency=payment.currency, payment_id=payment.id, order_id=payment.order_id,
        donation_id=donation_id or payment.donation_id, seller_order_id=seller_order_id or payment.seller_order_id,
        product_id=product_id, game_id=game_id, description=f"Verified payment {payment.provider}",
    )
    if to_money(service_fee_amount) > ZERO:
        record_entry(
            db, RevenueStream.SERVICE_FEE, service_fee_amount, f"svcfee:payment:{payment.id}",
            currency=payment.currency, payment_id=payment.id, order_id=payment.order_id,
            description="Service fee",
        )


def record_payment_processing_fee(db: DbSession, payment, fee: Decimal) -> None:
    if to_money(fee) <= ZERO:
        return
    record_entry(
        db, RevenueStream.PAYMENT_FEE, fee, f"payfee:payment:{payment.id}",
        currency=payment.currency, payment_id=payment.id, order_id=payment.order_id,
        description="Provider processing fee",
    )


def record_order_completion(db: DbSession, order: Order) -> None:
    """Per completed item: supplier cost + margin (profitability source of truth)."""
    for item in order.items:
        line_cost = to_money(Decimal(str(item.unit_cost)) * item.quantity)
        line_total = to_money(item.total)
        game_id = None
        product_id = None
        if item.variant_id:
            from vyron.db.models import Product, ProductVariant

            variant = db.get(ProductVariant, item.variant_id)
            if variant is not None:
                product_id = variant.product_id
                product = db.get(Product, variant.product_id)
                game_id = product.game_id if product else None
        if line_cost > ZERO:
            record_entry(
                db, RevenueStream.SUPPLIER_COST, line_cost, f"supcost:item:{item.id}",
                currency=order.currency, order_id=order.id, product_id=product_id, game_id=game_id,
                description=f"Supplier cost for {item.variant_name}",
            )
        margin = to_money(line_total - line_cost)
        if margin > ZERO:
            record_entry(
                db, RevenueStream.TOPUP_MARGIN, margin, f"margin:item:{item.id}",
                currency=order.currency, order_id=order.id, product_id=product_id, game_id=game_id,
                description=f"Margin for {item.variant_name}",
            )


def record_donation_fee(db: DbSession, donation) -> None:
    record_entry(
        db, RevenueStream.DONATION_FEE, donation.platform_fee, f"donfee:donation:{donation.id}",
        currency=donation.currency, donation_id=donation.id, payment_id=donation.payment_id,
        description="Donation platform fee",
    )


def record_marketplace_commission(db: DbSession, seller_order) -> None:
    record_entry(
        db, RevenueStream.MARKETPLACE_COMMISSION, seller_order.platform_fee, f"mktcomm:sellerorder:{seller_order.id}",
        currency=seller_order.currency, seller_order_id=seller_order.id, payment_id=seller_order.payment_id,
        description=f"Marketplace commission ({seller_order.commission_pct}%)",
    )


def record_promotion_fee(db: DbSession, promotion_purchase) -> None:
    record_entry(
        db, RevenueStream.PROMOTION_FEE, promotion_purchase.price, f"promo:listingpromotion:{promotion_purchase.id}",
        currency=promotion_purchase.currency, payment_id=promotion_purchase.payment_id,
        description=f"Listing promotion ({promotion_purchase.kind})",
    )


def record_subscription_fee(db: DbSession, subscription, amount: Decimal, currency: str, payment_id: Optional[str]) -> None:
    record_entry(
        db, RevenueStream.SUBSCRIPTION_FEE, amount, f"subfee:subscription:{subscription.id}",
        currency=currency, payment_id=payment_id, description="Seller subscription",
    )


def record_refund(db: DbSession, refund) -> None:
    record_entry(
        db, RevenueStream.REFUND, refund.amount, f"refund:{refund.id}",
        currency=refund.currency, payment_id=refund.payment_id, order_id=refund.order_id,
        description="Refund issued",
    )


def record_payout(db: DbSession, payout) -> None:
    record_entry(
        db, RevenueStream.SELLER_PAYOUT, payout.amount, f"payout:{payout.id}",
        currency=payout.currency, payout_id=payout.id, description="Seller payout completed",
    )


# --- reporting --------------------------------------------------------------------------
def _range_filter(start: Optional[datetime], end: Optional[datetime]):
    conditions = []
    if start:
        conditions.append(RevenueLedgerEntry.created_at >= start)
    if end:
        conditions.append(RevenueLedgerEntry.created_at <= end)
    return conditions


def summary(db: DbSession, start: Optional[datetime] = None, end: Optional[datetime] = None) -> Dict[str, Any]:
    """Totals per stream + derived business metrics for /admin/revenue."""
    rows = (
        db.query(RevenueLedgerEntry.stream, func.sum(RevenueLedgerEntry.amount))
        .filter(and_(True, *_range_filter(start, end)))
        .group_by(RevenueLedgerEntry.stream)
        .all()
    )
    totals: Dict[str, Decimal] = {stream.value: ZERO for stream in RevenueStream}
    for stream, total in rows:
        totals[str(stream)] = to_money(total or 0)

    gross = totals[RevenueStream.GROSS_REVENUE.value]
    supplier_costs = totals[RevenueStream.SUPPLIER_COST.value]
    topup_margin = totals[RevenueStream.TOPUP_MARGIN.value]
    marketplace_commission = totals[RevenueStream.MARKETPLACE_COMMISSION.value]
    donation_fees = totals[RevenueStream.DONATION_FEE.value]
    service_fees = totals[RevenueStream.SERVICE_FEE.value]
    promotion_fees = totals[RevenueStream.PROMOTION_FEE.value]
    subscription_fees = totals[RevenueStream.SUBSCRIPTION_FEE.value]
    payment_fees = totals[RevenueStream.PAYMENT_FEE.value]
    refunds = totals[RevenueStream.REFUND.value]
    payouts = totals[RevenueStream.SELLER_PAYOUT.value]

    platform_revenue = sum_money(topup_margin, marketplace_commission, donation_fees, service_fees, promotion_fees, subscription_fees)
    net_revenue = to_money(platform_revenue - payment_fees - refunds)

    return {
        "gross_revenue": gross,
        "supplier_costs": supplier_costs,
        "topup_margin": topup_margin,
        "marketplace_commission": marketplace_commission,
        "donation_fees": donation_fees,
        "service_fees": service_fees,
        "promotion_fees": promotion_fees,
        "subscription_fees": subscription_fees,
        "payment_fees": payment_fees,
        "refunds": refunds,
        "seller_payouts": payouts,
        "platform_revenue": platform_revenue,
        "net_revenue": net_revenue,
    }


def daily_series(db: DbSession, stream: Optional[str], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    date_col = func.date(RevenueLedgerEntry.created_at)
    query = db.query(date_col.label("day"), func.sum(RevenueLedgerEntry.amount))
    if stream:
        query = query.filter(RevenueLedgerEntry.stream == stream)
    query = query.filter(RevenueLedgerEntry.created_at >= start, RevenueLedgerEntry.created_at <= end)
    rows = query.group_by(date_col).order_by(date_col).all()
    return [{"day": str(day), "amount": str(to_money(total or 0))} for day, total in rows]


def by_game(db: DbSession, start: Optional[datetime], end: Optional[datetime], limit: int = 10) -> List[Dict[str, Any]]:
    from vyron.db.models import Game

    rows = (
        db.query(Game.name, RevenueLedgerEntry.stream, func.sum(RevenueLedgerEntry.amount))
        .join(RevenueLedgerEntry, RevenueLedgerEntry.game_id == Game.id)
        .filter(and_(RevenueLedgerEntry.game_id.isnot(None), *_range_filter(start, end)))
        .group_by(Game.name, RevenueLedgerEntry.stream)
        .all()
    )
    games: Dict[str, Dict[str, Decimal]] = {}
    for name, stream, total in rows:
        bucket = games.setdefault(str(name), {"gross": ZERO, "supplier_cost": ZERO, "margin": ZERO})
        if stream == RevenueStream.GROSS_REVENUE.value:
            bucket["gross"] += to_money(total or 0)
        elif stream == RevenueStream.SUPPLIER_COST.value:
            bucket["supplier_cost"] += to_money(total or 0)
        elif stream == RevenueStream.TOPUP_MARGIN.value:
            bucket["margin"] += to_money(total or 0)
    result = [
        {"game": name, "gross": str(v["gross"]), "supplier_cost": str(v["supplier_cost"]), "margin": str(v["margin"])}
        for name, v in games.items()
    ]
    result.sort(key=lambda r: Decimal(r["margin"]), reverse=True)
    return result[:limit]


def by_product(db: DbSession, start: Optional[datetime], end: Optional[datetime], limit: int = 10) -> List[Dict[str, Any]]:
    from vyron.db.models import Product

    rows = (
        db.query(Product.name, RevenueLedgerEntry.stream, func.sum(RevenueLedgerEntry.amount))
        .join(RevenueLedgerEntry, RevenueLedgerEntry.product_id == Product.id)
        .filter(and_(RevenueLedgerEntry.product_id.isnot(None), *_range_filter(start, end)))
        .group_by(Product.name, RevenueLedgerEntry.stream)
        .all()
    )
    products: Dict[str, Dict[str, Decimal]] = {}
    for name, stream, total in rows:
        bucket = products.setdefault(str(name), {"gross": ZERO, "supplier_cost": ZERO, "margin": ZERO})
        if stream == RevenueStream.GROSS_REVENUE.value:
            bucket["gross"] += to_money(total or 0)
        elif stream == RevenueStream.SUPPLIER_COST.value:
            bucket["supplier_cost"] += to_money(total or 0)
        elif stream == RevenueStream.TOPUP_MARGIN.value:
            bucket["margin"] += to_money(total or 0)
    result = [
        {"product": name, "gross": str(v["gross"]), "supplier_cost": str(v["supplier_cost"]), "margin": str(v["margin"])}
        for name, v in products.items()
    ]
    result.sort(key=lambda r: Decimal(r["margin"]), reverse=True)
    return result[:limit]


def by_stream(db: DbSession, start: Optional[datetime], end: Optional[datetime]) -> List[Dict[str, Any]]:
    data = summary(db, start, end)
    order = [
        ("topup_margin", "stream_TOPUP_MARGIN"),
        ("marketplace_commission", "stream_MARKETPLACE_COMMISSION"),
        ("donation_fees", "stream_DONATION_FEE"),
        ("service_fees", "stream_SERVICE_FEE"),
        ("promotion_fees", "stream_PROMOTION_FEE"),
        ("subscription_fees", "stream_SUBSCRIPTION_FEE"),
    ]
    return [{"key": label, "amount": str(data[key])} for key, label in order]


def order_profitability(db: DbSession, order: Order) -> Dict[str, Any]:
    """Per-order P&L: selling price, supplier cost, payment fee, platform fee, margin."""
    selling = to_money(order.total)
    supplier_cost = sum_money(*[to_money(Decimal(str(i.unit_cost)) * i.quantity) for i in order.items])
    rows = (
        db.query(RevenueLedgerEntry.stream, func.sum(RevenueLedgerEntry.amount))
        .filter(RevenueLedgerEntry.order_id == order.id)
        .group_by(RevenueLedgerEntry.stream)
        .all()
    )
    ledger = {str(s): to_money(t or 0) for s, t in rows}
    payment_fee = ledger.get(RevenueStream.PAYMENT_FEE.value, ZERO)
    service_fee = ledger.get(RevenueStream.SERVICE_FEE.value, ZERO)
    gross_margin = to_money(selling - supplier_cost)
    net = to_money(gross_margin + service_fee - payment_fee)
    return {
        "order_number": order.number,
        "selling_price": str(selling),
        "supplier_cost": str(supplier_cost),
        "payment_fee": str(payment_fee),
        "service_fee": str(service_fee),
        "gross_margin": str(gross_margin),
        "net_platform_revenue": str(net),
    }
