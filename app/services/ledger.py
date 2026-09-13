"""Financial revenue ledger + dashboard aggregates. Only verified transactions."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.pricing import q


def record(db: Session, kind: str, amount, order_id: int | None = None,
           currency: str = "UZS", note: str = "") -> models.RevenueLedger:
    row = models.RevenueLedger(kind=kind, amount=q(amount), order_id=order_id, currency=currency, note=note)
    db.add(row)
    db.flush()
    return row


KINDS = (
    "gross_sale", "supplier_cost", "payment_fee", "platform_fee",
    "marketplace_commission", "donation_fee", "seller_payout", "refund",
)


def summary(db: Session, date_from: dt.datetime | None = None, date_to: dt.datetime | None = None) -> dict:
    query = db.query(models.RevenueLedger.kind, func.coalesce(func.sum(models.RevenueLedger.amount), 0))
    if date_from:
        query = query.filter(models.RevenueLedger.created_at >= date_from)
    if date_to:
        query = query.filter(models.RevenueLedger.created_at <= date_to)
    query = query.group_by(models.RevenueLedger.kind)
    totals = {k: Decimal("0") for k in KINDS}
    for kind, total in query.all():
        totals[kind] = q(total or 0)
    gross = totals["gross_sale"]
    costs = totals["supplier_cost"] + totals["payment_fee"] + totals["seller_payout"] + totals["refund"]
    revenue = totals["platform_fee"] + totals["marketplace_commission"] + totals["donation_fee"]
    net = gross + revenue + costs  # costs stored as negatives, so add them
    orders_q = db.query(func.count(models.Order.id))
    if date_from:
        orders_q = orders_q.filter(models.Order.created_at >= date_from)
    if date_to:
        orders_q = orders_q.filter(models.Order.created_at <= date_to)
    orders = orders_q.scalar() or 0
    aov = (gross / orders).quantize(Decimal("0.01")) if orders else Decimal("0")
    return {
        "gross_revenue": gross,
        "supplier_costs": abs(totals["supplier_cost"]),
        "payment_fees": abs(totals["payment_fee"]),
        "platform_revenue": totals["platform_fee"],
        "marketplace_commission": totals["marketplace_commission"],
        "donation_fees": totals["donation_fee"],
        "seller_payouts": abs(totals["seller_payout"]),
        "refunds": abs(totals["refund"]),
        "net_profit": net,
        "orders": orders,
        "aov": aov,
    }
