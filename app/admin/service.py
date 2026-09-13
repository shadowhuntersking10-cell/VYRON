"""Admin dashboard metrics. All numbers come from verified DB rows only."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderStatus, Payment, PaymentStatus, RevenueLedger, SellerPayout, User


class AdminService:
    async def dashboard(self, db: AsyncSession) -> dict:
        total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        week_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
        active_users = (await db.execute(
            select(func.count(User.id)).where(User.last_login_at.is_not(None))
        )).scalar() or 0
        orders_total = (await db.execute(select(func.count(Order.id)))).scalar() or 0
        completed = (await db.execute(
            select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)
        )).scalar() or 0
        pending = (await db.execute(select(func.count(Order.id)).where(Order.status.in_(
            [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.PROCESSING,
             OrderStatus.SUPPLIER_PROCESSING, OrderStatus.MANUAL_REVIEW]
        )))).scalar() or 0

        rev = (await db.execute(select(
            func.coalesce(func.sum(RevenueLedger.gross), 0),
            func.coalesce(func.sum(RevenueLedger.supplier_cost), 0),
            func.coalesce(func.sum(RevenueLedger.net), 0),
        ))).first() or (0, 0, 0)
        payouts = (await db.execute(select(func.coalesce(func.sum(SellerPayout.amount), 0)))).scalar() or 0
        paid_volume = (await db.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.status == PaymentStatus.PAID))).scalar() or 0

        return {
            "total_users": total_users,
            "active_users": active_users,
            "orders": orders_total,
            "completed_orders": completed,
            "pending_orders": pending,
            "gross_revenue": float(rev[0]),
            "platform_revenue": float(rev[2]),
            "supplier_costs": float(rev[1]),
            "seller_payouts": float(payouts),
            "net_revenue": float(rev[2]),
            "paid_volume": float(paid_volume),
        }

    async def timeseries(self, db: AsyncSession, days: int = 30) -> list[dict]:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        rows = (await db.execute(select(
            func.date(RevenueLedger.created_at), func.coalesce(func.sum(RevenueLedger.net), 0),
        ).where(RevenueLedger.created_at >= since).group_by(func.date(RevenueLedger.created_at))
        .order_by(func.date(RevenueLedger.created_at)))).all()
        return [{"date": str(d), "net": float(n)} for d, n in rows]


_service: AdminService | None = None


def get_admin_service() -> AdminService:
    global _service
    if _service is None:
        _service = AdminService()
    return _service
