"""Fraud / risk engine.

Computes a 0-100 risk score from behavioral signals at payment confirmation
and order creation. High-risk orders go to MANUAL_REVIEW — the system never
auto-accuses: a human resolves every flagged case.

Signals (weights tuned conservatively):
- multiple failed payments (24h)
- rapid repeated orders (1h / 24h)
- repeated refunds (30d)
- multiple accounts ordering from one IP (24h)
- elevated stored user risk score
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import FraudEvent, Order, Payment, Refund, User
from vyron.enums import FraudEventType, PaymentStatus, RiskLevel, risk_level_for_score
from vyron.logging import get_logger

log = get_logger("vyron.fraud")


def _count_failed_payments(db: DbSession, user_id: str, hours: int = 24) -> int:
    since = utcnow() - timedelta(hours=hours)
    return (
        db.query(func.count(Payment.id))
        .filter(Payment.user_id == user_id, Payment.status == PaymentStatus.FAILED.value, Payment.created_at >= since)
        .scalar()
        or 0
    )


def _count_orders(db: DbSession, user_id: str, hours: int) -> int:
    since = utcnow() - timedelta(hours=hours)
    return (
        db.query(func.count(Order.id))
        .filter(Order.user_id == user_id, Order.created_at >= since)
        .scalar()
        or 0
    )


def _count_refunds(db: DbSession, user_id: str, days: int = 30) -> int:
    since = utcnow() - timedelta(days=days)
    return (
        db.query(func.count(Refund.id))
        .join(Order, Order.id == Refund.order_id)
        .filter(Order.user_id == user_id, Refund.created_at >= since)
        .scalar()
        or 0
    )


def _distinct_users_same_ip(db: DbSession, ip_address: Optional[str], hours: int = 24) -> int:
    if not ip_address:
        return 0
    since = utcnow() - timedelta(hours=hours)
    return (
        db.query(func.count(func.distinct(Order.user_id)))
        .filter(Order.ip_address == ip_address, Order.created_at >= since)
        .scalar()
        or 0
    )


def _recent_unresolved_event(db: DbSession, user_id: str, event_type: str, hours: int = 24) -> bool:
    since = utcnow() - timedelta(hours=hours)
    return (
        db.query(FraudEvent.id)
        .filter(
            FraudEvent.user_id == user_id,
            FraudEvent.type == event_type,
            FraudEvent.created_at >= since,
        )
        .first()
        is not None
    )


def assess(db: DbSession, user: User, order: Optional[Order] = None) -> Tuple[int, RiskLevel, List[Dict[str, Any]]]:
    """Compute the risk score and persist FraudEvents for triggered signals."""
    signals: List[Dict[str, Any]] = []
    score = 0

    failed_payments = _count_failed_payments(db, user.id)
    if failed_payments >= 3:
        score += min(30, failed_payments * 8)
        signals.append({"type": FraudEventType.FAILED_PAYMENTS.value, "count": failed_payments})

    orders_1h = _count_orders(db, user.id, 1)
    if orders_1h > 3:
        score += 25
        signals.append({"type": FraudEventType.RAPID_ORDERS.value, "count_1h": orders_1h})

    orders_24h = _count_orders(db, user.id, 24)
    if orders_24h > 8:
        score += 20
        signals.append({"type": FraudEventType.UNUSUAL_FREQUENCY.value, "count_24h": orders_24h})

    refunds = _count_refunds(db, user.id)
    if refunds > 2:
        score += 20
        signals.append({"type": FraudEventType.REFUND_ABUSE.value, "count": refunds})

    if order and order.ip_address:
        ip_users = _distinct_users_same_ip(db, order.ip_address)
        if ip_users > 3:
            score += 15
            signals.append({"type": FraudEventType.SUSPICIOUS_PATTERN.value, "ip_user_count": ip_users})

    if user.fraud_risk_score > 40:
        score += int(user.fraud_risk_score * 0.3)

    score = max(0, min(100, score))
    level = risk_level_for_score(score)

    for signal in signals:
        event_type = signal.pop("type")
        if _recent_unresolved_event(db, user.id, event_type):
            continue
        db.add(
            FraudEvent(
                user_id=user.id,
                order_id=order.id if order else None,
                type=event_type,
                risk_score=score,
                level=level.value,
                signals=signal,
                description=f"{event_type} detected for user {user.username} (score {score})",
            )
        )

    # decay-and-max update of the stored user score
    user.fraud_risk_score = max(score, int(user.fraud_risk_score * 0.8)) if score else max(0, int(user.fraud_risk_score * 0.9))
    db.flush()
    if signals:
        log.warning("fraud signals", user=user.username, score=score, level=level.value, signals=signals)
    return score, level, signals


def assess_and_store_order(db: DbSession, order: Order) -> Tuple[int, RiskLevel]:
    user = db.get(User, order.user_id)
    if user is None:
        return 0, RiskLevel.LOW
    score, level, _ = assess(db, user, order)
    order.risk_score = score
    order.risk_level = level.value
    db.flush()
    return score, level


def resolve_event(db: DbSession, event: FraudEvent, admin: User, resolution: str) -> FraudEvent:
    event.resolved = True
    event.resolution = resolution[:300]
    event.resolved_by = admin.id
    event.resolved_at = utcnow()
    db.commit()
    return event
