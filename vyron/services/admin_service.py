"""Admin service — dashboard statistics, user management, queue health.

All figures are computed server-side from verified data only (paid payments,
completed events, the revenue ledger). Unpaid orders never inflate revenue.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import (
    Donation,
    FraudEvent,
    Game,
    Notification,
    Order,
    Payment,
    PayoutRequest,
    Product,
    SellerListing,
    SellerProfile,
    Supplier,
    SupportTicket,
    TelegramConnection,
    User,
)
from vyron.enums import (
    ADMIN_ROLES,
    DonationStatus,
    ListingStatus,
    OrderStatus,
    PaymentStatus,
    PayoutStatus,
    QueueName,
    TicketStatus,
    UserRole,
    UserStatus,
)
from vyron.errors import ForbiddenError, NotFoundError, ValidationError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.services import audit_service, revenue_service

log = get_logger("vyron.admin")


def range_bounds(days: Optional[int], start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime]:
    now = utcnow()
    if start:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    else:
        start_dt = now - timedelta(days=max(1, days or 30))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else now
    if start_dt.tzinfo is None:

        start_dt = start_dt.replace(tzinfo=UTC)
    if end_dt.tzinfo is None:

        end_dt = end_dt.replace(tzinfo=UTC)
    return start_dt, end_dt


def dashboard_stats(db: DbSession, days: int = 30) -> Dict[str, Any]:
    start, end = range_bounds(days, None, None)

    users_total = db.query(func.count(User.id)).scalar() or 0
    users_new = db.query(func.count(User.id)).filter(User.created_at >= start).scalar() or 0
    orders_total = db.query(func.count(Order.id)).scalar() or 0
    orders_completed = db.query(func.count(Order.id)).filter(Order.status == OrderStatus.COMPLETED.value).scalar() or 0
    orders_review = db.query(func.count(Order.id)).filter(Order.status == OrderStatus.MANUAL_REVIEW.value).scalar() or 0
    sellers_total = db.query(func.count(SellerProfile.id)).scalar() or 0
    listings_pending = (
        db.query(func.count(SellerListing.id)).filter(SellerListing.status == ListingStatus.PENDING_REVIEW.value).scalar() or 0
    )
    donations_total = (
        db.query(func.coalesce(func.sum(Donation.amount), 0))
        .filter(Donation.status == DonationStatus.COMPLETED.value, Donation.completed_at >= start)
        .scalar()
    )
    donations_count = (
        db.query(func.count(Donation.id))
        .filter(Donation.status == DonationStatus.COMPLETED.value, Donation.completed_at >= start)
        .scalar()
        or 0
    )
    payments_failed = db.query(func.count(Payment.id)).filter(Payment.status == PaymentStatus.FAILED.value, Payment.created_at >= start).scalar() or 0
    payments_pending = db.query(func.count(Payment.id)).filter(Payment.status.in_([PaymentStatus.PENDING.value, PaymentStatus.PROCESSING.value])).scalar() or 0
    supplier_errors = db.query(func.count(Supplier.id)).filter(Supplier.status == "ERROR").scalar() or 0
    fraud_alerts = db.query(func.count(FraudEvent.id)).filter(FraudEvent.resolved.is_(False), FraudEvent.created_at >= start).scalar() or 0
    payout_requests = db.query(func.count(PayoutRequest.id)).filter(PayoutRequest.status.in_([PayoutStatus.PENDING.value, PayoutStatus.APPROVED.value])).scalar() or 0
    tickets_open = db.query(func.count(SupportTicket.id)).filter(SupportTicket.status.in_([TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value])).scalar() or 0
    telegram_connections = db.query(func.count(TelegramConnection.id)).scalar() or 0

    revenue = revenue_service.summary(db, start, end)

    return {
        "range_days": days,
        "users_total": users_total,
        "users_new": users_new,
        "orders_total": orders_total,
        "orders_completed": orders_completed,
        "orders_review": orders_review,
        "sellers_total": sellers_total,
        "listings_pending": listings_pending,
        "donations_total": str(to_money(donations_total)),
        "donations_count": donations_count,
        "payments_failed": payments_failed,
        "payments_pending": payments_pending,
        "supplier_errors": supplier_errors,
        "fraud_alerts": fraud_alerts,
        "payout_requests": payout_requests,
        "tickets_open": tickets_open,
        "telegram_connections": telegram_connections,
        "revenue": {k: str(v) for k, v in revenue.items()},
    }


def chart_series(db: DbSession, days: int = 30) -> Dict[str, List[Dict[str, Any]]]:
    start, end = range_bounds(days, None, None)

    def _series(model, date_col, value=None, extra_filter=None) -> List[Dict[str, Any]]:
        day = func.date(date_col)
        expr = func.sum(value) if value is not None else func.count(model.id)
        query = db.query(day.label("d"), expr).filter(date_col >= start, date_col <= end)
        if extra_filter is not None:
            query = query.filter(extra_filter)
        rows = query.group_by(day).order_by(day).all()
        return [{"day": str(d), "value": str(to_money(v)) if value is not None else int(v or 0)} for d, v in rows]

    daily_revenue = revenue_service.daily_series(db, "GROSS_REVENUE", start, end)
    daily_orders = _series(Order, Order.created_at)
    daily_new_users = _series(User, User.created_at)
    daily_donations = _series(
        Donation, Donation.created_at, Donation.amount, Donation.status == DonationStatus.COMPLETED.value
    )
    return {
        "daily_revenue": [{"day": r["day"], "value": r["amount"]} for r in daily_revenue],
        "daily_orders": daily_orders,
        "daily_new_users": daily_new_users,
        "daily_donations": daily_donations,
    }


# --- user management ------------------------------------------------------------------
def search_users(db: DbSession, query: Optional[str], role: Optional[str], status: Optional[str], page: int, page_size: int = 20) -> Dict[str, Any]:
    q = db.query(User)
    if query:
        like = f"%{query.strip()[:60]}%"
        q = q.filter(func.lower(User.username).like(like.lower()) | func.lower(User.email).like(like.lower()) | User.name.like(like))
    if role:
        q = q.filter(User.role == role)
    if status:
        q = q.filter(User.status == status)
    total = q.count()
    items = q.order_by(User.created_at.desc()).offset((max(1, page) - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def set_user_status(db: DbSession, admin: User, target: User, status: str, reason: Optional[str] = None) -> User:
    if status not in {s.value for s in UserStatus}:
        raise ValidationError("Invalid status.", code="STATUS_INVALID")
    if target.id == admin.id and status != UserStatus.ACTIVE.value:
        raise ValidationError("You cannot disable your own account here.", code="SELF_DISABLE")
    if UserRole(target.role) in ADMIN_ROLES and not (UserRole(admin.role) == UserRole.SUPER_ADMIN):
        raise ForbiddenError("Only SUPER_ADMIN can change staff/admin account status.", code="FORBIDDEN")
    before = target.status
    target.status = status
    if status != UserStatus.ACTIVE.value:
        from vyron.security.sessions import revoke_all_user_sessions

        db.commit()
        revoke_all_user_sessions(db, target.id)
    db.commit()
    audit_service.record_admin_action(db, admin, f"user.{status.lower()}", target_type="user", target_id=target.id, reason=reason, data={"before": before, "after": status})
    return target


def change_user_role(db: DbSession, admin: User, target: User, role: str, reason: Optional[str] = None) -> User:
    if role not in {r.value for r in UserRole}:
        raise ValidationError("Invalid role.", code="ROLE_INVALID")
    # Privilege-escalation guard: only SUPER_ADMIN may grant SUPER_ADMIN.
    if role == UserRole.SUPER_ADMIN.value and admin.role != UserRole.SUPER_ADMIN.value:
        raise ForbiddenError("Only a SUPER_ADMIN can grant the SUPER_ADMIN role.", code="ESCALATION_FORBIDDEN")
    # Admins may not modify roles at or above their own level (except SUPER_ADMIN operating on others).
    from vyron.enums import ROLE_LEVELS

    if admin.role != UserRole.SUPER_ADMIN.value and ROLE_LEVELS.get(UserRole(role), 0) >= ROLE_LEVELS.get(UserRole(admin.role), 0):
        raise ForbiddenError("You cannot assign a role equal to or above your own.", code="ESCALATION_FORBIDDEN")
    before = target.role
    target.role = role
    db.commit()
    audit_service.record_admin_action(db, admin, "user.role_changed", target_type="user", target_id=target.id, reason=reason, data={"before": before, "after": role})
    return target


def user_detail(db: DbSession, user_id: str) -> Dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")
    orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(20).all()
    payments = (
        db.query(Payment).filter(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(20).all()
    )
    fraud_events = db.query(FraudEvent).filter(FraudEvent.user_id == user.id).order_by(FraudEvent.created_at.desc()).limit(20).all()
    audits = (
        db.query(audit_model())
        .filter(audit_model().actor_id == user.id)
        .order_by(audit_model().created_at.desc())
        .limit(20)
        .all()
    )
    return {"user": user, "orders": orders, "payments": payments, "fraud_events": fraud_events, "audit_logs": audits}


def audit_model():
    from vyron.db.models import AuditLog

    return AuditLog


# --- queue health -----------------------------------------------------------------------
def queue_health() -> Dict[str, Any]:
    from vyron.queue.engine import Queue

    health: Dict[str, Any] = {"queues": [], "redis": False}
    try:
        from vyron.redis_client import redis_ping

        health["redis"] = redis_ping()
    except Exception:
        health["redis"] = False
    for queue_name in QueueName:
        queue = Queue(queue_name.value)
        health["queues"].append({"name": queue_name.value, "depth": queue.depth(), "dlq": queue.dlq_depth()})
    return health


def notify_users(db: DbSession, admin: User, title: str, body: str, user_ids: Optional[List[str]] = None) -> int:
    """Admin → users broadcast/targeted notification."""
    query = db.query(User)
    if user_ids:
        query = query.filter(User.id.in_(user_ids))
    count = 0
    for user in query.all():
        db.add(Notification(user_id=user.id, type="MARKETING", title=title[:200], body=body[:2000]))
        count += 1
    db.commit()
    audit_service.record_admin_action(db, admin, "notification.sent", data={"recipients": count, "title": title[:100]})
    return count


def catalog_counts(db: DbSession) -> Dict[str, int]:
    return {
        "games": db.query(func.count(Game.id)).scalar() or 0,
        "games_active": db.query(func.count(Game.id)).filter(Game.status == "ACTIVE").scalar() or 0,
        "products": db.query(func.count(Product.id)).scalar() or 0,
        "products_active": db.query(func.count(Product.id)).filter(Product.active.is_(True)).scalar() or 0,
        "suppliers": db.query(func.count(Supplier.id)).scalar() or 0,
        "suppliers_active": db.query(func.count(Supplier.id)).filter(Supplier.active.is_(True)).scalar() or 0,
    }
