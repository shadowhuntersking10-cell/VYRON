"""Donation platform service.

Security rules (spec Phase 19/20 + revenue model):
- amounts are computed SERVER-SIDE (gross = requested, fee = configured,
  net = gross - fee) — the client never sends a fee or net amount
- a donation only completes from a VERIFIED provider webhook
- duplicate protection via idempotency keys and unique DonationTransaction
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import Donation, DonationPage, DonationTransaction, Payment, User
from vyron.enums import DonationStatus, PaymentPurpose
from vyron.errors import NotFoundError, ValidationError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.services import notification_service, revenue_service, settings_service

log = get_logger("vyron.donations")

MIN_DONATION = Decimal("1.00")
MAX_DONATION = Decimal("100000.00")


def ensure_page(db: DbSession, user: User) -> DonationPage:
    page = db.query(DonationPage).filter(DonationPage.user_id == user.id).first()
    if page is None:
        page = DonationPage(user_id=user.id, currency="USD", active=True)
        db.add(page)
        db.commit()
    return page


def update_page(
    db: DbSession,
    user: User,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    goal_amount: Optional[Decimal] = None,
    active: Optional[bool] = None,
) -> DonationPage:
    page = ensure_page(db, user)
    if title is not None:
        page.title = title.strip()[:160] or None
    if description is not None:
        page.description = description.strip()[:2000] or None
    if goal_amount is not None:
        if goal_amount <= 0:
            raise ValidationError("Goal must be positive.", code="GOAL_INVALID")
        page.goal_amount = to_money(goal_amount)
    if active is not None:
        page.active = bool(active)
    db.commit()
    return page


def get_public_page(db: DbSession, username: str) -> Dict[str, Any]:
    user = db.query(User).filter(User.username == (username or "").strip().lower()).first()
    if user is None:
        raise NotFoundError("Donation page not found.")
    page = db.query(DonationPage).filter(DonationPage.user_id == user.id, DonationPage.active.is_(True)).first()
    if page is None:
        raise NotFoundError("Donation page not found or disabled.")

    totals = (
        db.query(func.coalesce(func.sum(Donation.amount), 0), func.count(Donation.id))
        .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value)
        .one()
    )
    recent = (
        db.query(Donation)
        .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value)
        .order_by(Donation.completed_at.desc())
        .limit(20)
        .all()
    )
    top_rows = (
        db.query(
            func.coalesce(func.sum(Donation.amount), 0).label("total"),
            Donation.donor_name,
            Donation.anonymous,
            Donation.donor_user_id,
        )
        .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value, Donation.anonymous.is_(False))
        .group_by(Donation.donor_user_id, Donation.donor_name, Donation.anonymous)
        .order_by(func.sum(Donation.amount).desc())
        .limit(10)
        .all()
    )
    return {
        "page": page,
        "user": user,
        "raised": to_money(totals[0]),
        "count": int(totals[1]),
        "recent": recent,
        "top_supporters": [
            {"name": (row.donor_name or "Supporter")[:60], "total": to_money(row.total)} for row in top_rows
        ],
    }


def create_donation(
    db: DbSession,
    page: DonationPage,
    *,
    gross_amount: Decimal,
    donor_user: Optional[User],
    donor_name: Optional[str],
    donor_email: Optional[str],
    message: Optional[str],
    anonymous: bool,
    provider_name: Optional[str],
    idempotency_key: Optional[str],
    ip_address: Optional[str],
) -> tuple[Donation, Payment]:
    gross = to_money(gross_amount)
    if gross < MIN_DONATION or gross > MAX_DONATION:
        raise ValidationError(f"Donation amount must be between {MIN_DONATION} and {MAX_DONATION}.", code="AMOUNT_INVALID")

    if idempotency_key:
        existing = db.query(Donation).filter(Donation.idempotency_key == idempotency_key).first()
        if existing:
            payment = (
                db.query(Payment)
                .filter(Payment.donation_id == existing.id)
                .order_by(Payment.created_at.desc())
                .first()
            )
            if payment:
                return existing, payment

    # SERVER-SIDE fee computation — transparent at checkout, never client-supplied.
    fee = settings_service.donation_fee(db, gross)
    net = to_money(gross - fee)

    donation = Donation(
        page_id=page.id,
        donor_user_id=donor_user.id if donor_user else None,
        donor_name=(donor_name or "").strip()[:120] or None,
        donor_email=(donor_email or "").strip().lower()[:255] or None,
        message=(message or "").strip()[:500] or None,
        anonymous=bool(anonymous),
        amount=net,
        platform_fee=fee,
        gross_amount=gross,
        currency=page.currency or "USD",
        status=DonationStatus.PENDING.value,
        idempotency_key=idempotency_key,
        ip_address=ip_address,
    )
    db.add(donation)
    db.flush()

    from vyron.services import payment_service

    recipient = db.get(User, page.user_id)
    payment = payment_service.create_payment(
        db,
        purpose=PaymentPurpose.DONATION,
        amount=gross,
        currency=donation.currency,
        description=f"Donation for {recipient.username if recipient else 'creator'}",
        user=donor_user,
        provider_name=provider_name,
        donation=donation,
        metadata={"donation_id": donation.id},
    )
    donation.payment_id = payment.id
    db.commit()
    return donation, payment


def complete_donation(db: DbSession, donation: Donation, payment: Payment) -> None:
    """Called ONLY from verified payment confirmation (webhook/reconciliation)."""
    if donation.status == DonationStatus.COMPLETED.value:
        return
    donation.status = DonationStatus.COMPLETED.value
    donation.completed_at = utcnow()
    donation.payment_id = payment.id

    db.add(
        DonationTransaction(
            donation_id=donation.id,
            payment_id=payment.id,
            recipient_user_id=donation.page.user_id,
            donor_user_id=donation.donor_user_id,
            gross_amount=to_money(donation.gross_amount),
            platform_fee=to_money(donation.platform_fee),
            net_amount=to_money(donation.amount),
            currency=donation.currency,
            anonymous=donation.anonymous,
            message=donation.message,
        )
    )
    revenue_service.record_verified_payment(db, payment, donation_id=donation.id)
    revenue_service.record_donation_fee(db, donation)

    recipient = db.get(User, donation.page.user_id)
    if recipient:
        from vyron.i18n import t

        display_donor = t("notify.anonymous_donor", recipient.locale) if donation.anonymous else (donation.donor_name or t("notify.anonymous_donor", recipient.locale))
        message_part = ""
        if donation.message:
            message_part = t("notify.donation_message_part", recipient.locale, message=donation.message[:200])
        notification_service.notify_event(
            db,
            recipient,
            "donation_received",
            {
                "donor": display_donor,
                "amount": f"{donation.amount} {donation.currency}",
                "message_part": message_part,
                "message": donation.message or "",
            },
            link=f"/donate/{recipient.username}",
            commit=False,
        )
    db.flush()
    log.info("donation completed", donation=donation.id, amount=str(donation.amount))


def fail_donation(db: DbSession, donation: Donation) -> None:
    if donation.status == DonationStatus.PENDING.value:
        donation.status = DonationStatus.FAILED.value
        db.commit()


def user_donation_stats(db: DbSession, user: User) -> Dict[str, Any]:
    page = db.query(DonationPage).filter(DonationPage.user_id == user.id).first()
    if page is None:
        return {"received": to_money(0), "count": 0, "given": to_money(0), "given_count": 0}
    received = (
        db.query(func.coalesce(func.sum(Donation.amount), 0))
        .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value)
        .scalar()
    )
    received_count = (
        db.query(func.count(Donation.id))
        .filter(Donation.page_id == page.id, Donation.status == DonationStatus.COMPLETED.value)
        .scalar()
    )
    given = (
        db.query(func.coalesce(func.sum(Donation.amount), 0))
        .filter(Donation.donor_user_id == user.id, Donation.status == DonationStatus.COMPLETED.value)
        .scalar()
    )
    given_count = (
        db.query(func.count(Donation.id))
        .filter(Donation.donor_user_id == user.id, Donation.status == DonationStatus.COMPLETED.value)
        .scalar()
    )
    return {
        "received": to_money(received),
        "count": int(received_count or 0),
        "given": to_money(given),
        "given_count": int(given_count or 0),
        "page_active": bool(page.active),
        "goal": to_money(page.goal_amount) if page.goal_amount else None,
    }
