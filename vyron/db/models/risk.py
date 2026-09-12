"""Fraud, audit and admin action records."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vyron.db.base import GUID, Base, UTCDateTime, new_id, utcnow
from vyron.enums import FraudEventType, RiskLevel


class FraudEvent(Base):
    __tablename__ = "fraud_events"
    __table_args__ = (Index("ix_fraud_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    user_id: Mapped[Optional[str]] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    payment_id: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(28), nullable=False, default=FraudEventType.SUSPICIOUS_PATTERN.value, index=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default=RiskLevel.LOW.value, index=True)
    signals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(GUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)


class AuditLog(Base):
    """System-wide audit trail (auth events, webhooks, supplier attempts, admin ops, errors)."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False, default="SYSTEM")  # USER|ADMIN|SYSTEM|WEBHOOK|BOT
    actor_role: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    before: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)


class AdminAction(Base):
    """Explicit record of consequential admin decisions (role changes, bans, refunds...)."""

    __tablename__ = "admin_actions"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=new_id)
    admin_id: Mapped[str] = mapped_column(GUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, default=utcnow, index=True)
