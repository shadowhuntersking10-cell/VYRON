"""Payment service — creation, webhook processing, reconciliation, refunds.

Core guarantees:
- the FRONTEND never determines payment success; only provider-verified events
- webhooks are signature-verified, amount-checked and idempotent
  (unique (provider, event_id) — a webhook arriving five times processes once)
- PAYMENT_PENDING -> PAID happens exclusively here, inside one transaction
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional
from urllib.parse import quote

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from vyron.config import settings
from vyron.db.base import utcnow
from vyron.db.models import (
    Donation,
    FraudEvent,
    ListingPromotion,
    Order,
    Payment,
    PaymentWebhook,
    Refund,
    SellerOrder,
    SellerSubscription,
    Transaction,
    User,
)
from vyron.enums import (
    FraudEventType,
    OrderStatus,
    PaymentPurpose,
    PaymentStatus,
    QueueName,
    RefundStatus,
    RiskLevel,
    TransactionType,
)
from vyron.errors import NotFoundError, PaymentError, ValidationError, WebhookVerificationError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.payments.base import PaymentRequest, WebhookRequest
from vyron.payments.registry import get_provider
from vyron.queue.engine import Queue
from vyron.services import audit_service, fraud_service, notification_service, order_service, revenue_service

log = get_logger("vyron.payments")

PENDING_RECONCILE_MINUTES = 10


def _return_urls(payment_id: str) -> tuple[str, str]:
    base = settings.public_base_url.rstrip("/")
    success = settings.payment_success_redirect or "/dashboard/orders"
    cancel = settings.payment_cancel_redirect or "/checkout/cancelled"
    sep_s = "&" if "?" in success else "?"
    sep_c = "&" if "?" in cancel else "?"
    return f"{base}{success}{sep_s}payment={quote(payment_id)}", f"{base}{cancel}{sep_c}payment={quote(payment_id)}"


def create_payment(
    db: DbSession,
    *,
    purpose: PaymentPurpose | str,
    amount: Decimal,
    currency: str,
    description: str,
    user: Optional[User],
    provider_name: Optional[str] = None,
    order: Optional[Order] = None,
    donation: Optional[Donation] = None,
    seller_order: Optional[SellerOrder] = None,
    promotion: Optional[ListingPromotion] = None,
    subscription: Optional[SellerSubscription] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Payment:
    purpose = PaymentPurpose(purpose) if not isinstance(purpose, PaymentPurpose) else purpose
    provider = get_provider(provider_name)
    if not provider.is_configured():
        from vyron.errors import ProviderNotConfiguredError

        raise ProviderNotConfiguredError(
            f"Payment provider '{provider.name}' is not configured.", code="PAYMENT_PROVIDER_NOT_CONFIGURED"
        )

    entity_id = (order.id if order else donation.id if donation else seller_order.id if seller_order else promotion.id if promotion else subscription.id if subscription else None)
    idem_key = f"{purpose.value}:{entity_id}" if entity_id else None

    # Idempotent: reuse an unfinished payment for the same entity+provider.
    if idem_key:
        existing = (
            db.query(Payment)
            .filter(Payment.idempotency_key == idem_key, Payment.provider == provider.name)
            .filter(Payment.status.in_([PaymentStatus.PENDING.value, PaymentStatus.PROCESSING.value]))
            .first()
        )
        if existing and existing.checkout_url:
            return existing
        if existing:
            payment = existing
        else:
            payment = None
    else:
        payment = None

    if payment is None:
        payment = Payment(
            order_id=order.id if order else None,
            donation_id=donation.id if donation else None,
            seller_order_id=seller_order.id if seller_order else None,
            listing_promotion_id=promotion.id if promotion else None,
            seller_subscription_id=subscription.id if subscription else None,
            user_id=user.id if user else (order.user_id if order else None),
            purpose=purpose.value,
            provider=provider.name,
            status=PaymentStatus.PENDING.value,
            amount=to_money(amount),
            currency=currency.upper(),
            idempotency_key=idem_key,
            metadata_=metadata or {},
        )
        db.add(payment)
        db.flush()

    return_url, cancel_url = _return_urls(payment.id)
    request = PaymentRequest(
        payment_id=payment.id,
        amount=to_money(amount),
        currency=currency.upper(),
        description=description[:250],
        return_url=return_url,
        cancel_url=cancel_url,
        metadata={
            "payment_id": payment.id,
            "purpose": purpose.value,
            "order_number": order.number if order else (seller_order.number if seller_order else ""),
            **(metadata or {}),
        },
        idempotency_key=f"pay-{payment.id}",
    )
    result = provider.create_payment(request)
    payment.provider_payment_id = result.provider_payment_id
    payment.checkout_url = result.checkout_url
    if result.status == "PAID":
        # Some providers confirm instantly — still record via the same code path.
        _apply_provider_result_paid(db, payment, result.amount)
    db.commit()

    if order is not None and order.status == OrderStatus.CREATED.value:
        order_service.transition(db, order, OrderStatus.PAYMENT_PENDING, reason="Payment created", actor_type="SYSTEM")
    audit_service.record_audit(
        db, "payment.created", actor_id=payment.user_id, actor_type="USER", entity_type="payment", entity_id=payment.id,
        after={"provider": payment.provider, "amount": str(payment.amount), "currency": payment.currency},
    )
    return payment


def _apply_provider_result_paid(db: DbSession, payment: Payment, amount: Optional[Decimal]) -> None:
    """Handle instant-confirmation from create/verify calls (same guarantees as webhook)."""
    if amount is not None and to_money(amount) != to_money(payment.amount):
        log.error("amount mismatch on instant confirmation", payment=payment.id)
        return
    mark_paid(db, payment, source="provider_result")


# --- webhooks -------------------------------------------------------------------------------
def handle_webhook(db: DbSession, provider_name: str, request: WebhookRequest, ip_address: Optional[str]) -> Dict[str, Any]:
    provider = get_provider(provider_name)

    try:
        event = provider.parse_webhook(request)
    except WebhookVerificationError as exc:
        _record_webhook(db, provider_name, event_id=f"invalid-{utcnow().timestamp()}", payload=None, signature_valid=False, error=str(exc), ip_address=ip_address)
        raise
    except Exception as exc:
        _record_webhook(db, provider_name, event_id=f"error-{utcnow().timestamp()}", payload=None, signature_valid=False, error=str(exc)[:500], ip_address=ip_address)
        raise WebhookVerificationError(f"Webhook could not be parsed: {exc}") from exc

    duplicate = False
    try:
        webhook = _record_webhook(
            db, provider_name, event_id=event.event_id, event_type=event.event_type,
            payload=event.raw, signature_valid=True, ip_address=ip_address, commit=False,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = True
        webhook = (
            db.query(PaymentWebhook)
            .filter(PaymentWebhook.provider == provider_name, PaymentWebhook.event_id == event.event_id)
            .first()
        )
        log.info("duplicate webhook ignored", provider=provider_name, event_id=event.event_id)

    if duplicate:
        return {"success": True, "duplicate": True, "event_id": event.event_id}

    payment = _resolve_payment(db, event.merchant_reference, event.provider_payment_id)
    if payment is None:
        webhook.processed = True
        webhook.processing_error = "payment not found for event"
        webhook.processed_at = utcnow()
        db.commit()
        log.warning("webhook without matching payment", provider=provider_name, event=event.event_type, ref=event.merchant_reference)
        return {"success": True, "matched": False, "event_id": event.event_id}

    try:
        if event.status == "PAID":
            if event.amount is not None and to_money(event.amount) != to_money(payment.amount):
                # Amount tampering / mismatch — never mark paid; flag for humans.
                webhook.processed = True
                webhook.processing_error = f"amount mismatch: expected {payment.amount}, got {event.amount}"
                webhook.processed_at = utcnow()
                _flag_amount_mismatch(db, payment, event)
                db.commit()
                log.error("webhook amount mismatch", payment=payment.id, expected=str(payment.amount), got=str(event.amount))
                return {"success": True, "matched": True, "amount_mismatch": True}
            mark_paid(db, payment, source="webhook", provider_event=event.event_type)
        elif event.status in {"FAILED", "CANCELLED", "EXPIRED"}:
            mark_failed(db, payment, reason=f"provider: {event.event_type}")
        elif event.status == "REFUNDED":
            _handle_provider_refund(db, payment, event)
        webhook.processed = True
        webhook.payment_id = payment.id
        webhook.processed_at = utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        webhook.processing_error = str(exc)[:500]
        db.commit()
        log.exception(f"webhook processing failed for {event.event_id}")
        raise
    return {"success": True, "matched": True, "event_id": event.event_id}


def _record_webhook(
    db: DbSession,
    provider: str,
    event_id: str,
    payload: Optional[dict],
    signature_valid: bool,
    event_type: Optional[str] = None,
    error: Optional[str] = None,
    ip_address: Optional[str] = None,
    commit: bool = True,
) -> PaymentWebhook:
    webhook = PaymentWebhook(
        provider=provider,
        event_id=event_id[:190],
        event_type=(event_type or "")[:80] or None,
        payload=payload,
        signature_valid=signature_valid,
        processing_error=(error or "")[:500] or None,
        ip_address=ip_address,
    )
    db.add(webhook)
    if commit:
        db.commit()
    else:
        db.flush()
    return webhook


def _resolve_payment(db: DbSession, merchant_reference: Optional[str], provider_payment_id: Optional[str]) -> Optional[Payment]:
    if merchant_reference:
        payment = db.get(Payment, merchant_reference)
        if payment:
            return payment
    if provider_payment_id:
        return (
            db.query(Payment)
            .filter(Payment.provider_payment_id == provider_payment_id)
            .order_by(Payment.created_at.desc())
            .first()
        )
    return None


def _flag_amount_mismatch(db: DbSession, payment: Payment, event) -> None:
    order = db.get(Order, payment.order_id) if payment.order_id else None
    if order is not None and order.status in {OrderStatus.PAYMENT_PENDING.value, OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
        try:
            order_service.transition(db, order, OrderStatus.MANUAL_REVIEW, reason="Payment amount mismatch", actor_type="WEBHOOK", commit=False)
        except Exception:
            pass
    db.add(
        FraudEvent(
            user_id=payment.user_id,
            order_id=payment.order_id,
            payment_id=payment.id,
            type=FraudEventType.SUSPICIOUS_PATTERN.value,
            risk_score=85,
            level=RiskLevel.CRITICAL.value,
            signals={"expected_amount": str(payment.amount), "claimed_amount": str(event.amount)},
            description="Webhook amount mismatch — possible tampering attempt",
        )
    )


# --- state application -----------------------------------------------------------------------
def mark_paid(db: DbSession, payment: Payment, source: str = "webhook", provider_event: str = "") -> None:
    if payment.status == PaymentStatus.PAID.value:
        return  # idempotent
    if payment.status in {PaymentStatus.REFUNDED.value, PaymentStatus.PARTIALLY_REFUNDED.value}:
        log.warning("mark_paid on refunded payment ignored", payment=payment.id)
        return
    payment.status = PaymentStatus.PAID.value
    payment.paid_at = utcnow()

    db.add(
        Transaction(
            type=TransactionType.PAYMENT_IN.value,
            amount=to_money(payment.amount),
            currency=payment.currency,
            payment_id=payment.id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            description=f"Incoming payment via {payment.provider} ({source})",
            idempotency_key=f"tx:payin:{payment.id}",
        )
    )
    db.flush()

    purpose = payment.purpose
    if purpose == PaymentPurpose.ORDER.value and payment.order_id:
        _on_order_paid(db, payment)
    elif purpose == PaymentPurpose.DONATION.value and payment.donation_id:
        from vyron.services import donation_service

        donation = db.get(Donation, payment.donation_id)
        if donation:
            donation_service.complete_donation(db, donation, payment)
    elif purpose == PaymentPurpose.MARKETPLACE_ORDER.value and payment.seller_order_id:
        from vyron.services import seller_service

        seller_order = db.get(SellerOrder, payment.seller_order_id)
        if seller_order:
            seller_service.on_marketplace_order_paid(db, seller_order, payment)
    elif purpose == PaymentPurpose.PROMOTION.value and payment.listing_promotion_id:
        from vyron.services import seller_service

        promo = db.get(ListingPromotion, payment.listing_promotion_id)
        if promo:
            seller_service.activate_promotion(db, promo, payment)
    elif purpose == PaymentPurpose.SUBSCRIPTION.value and payment.seller_subscription_id:
        from vyron.services import seller_service

        subscription = db.get(SellerSubscription, payment.seller_subscription_id)
        if subscription:
            seller_service.activate_subscription(db, subscription, payment)

    audit_service.record_audit(
        db, "payment.paid", actor_type="WEBHOOK", entity_type="payment", entity_id=payment.id,
        after={"status": payment.status, "amount": str(payment.amount), "source": source, "event": provider_event}, commit=False,
    )
    db.commit()
    log.info("payment marked PAID", payment=payment.id, purpose=purpose, source=source)


def _on_order_paid(db: DbSession, payment: Payment) -> None:
    order = db.get(Order, payment.order_id)
    if order is None:
        return
    if order.status not in {OrderStatus.PAYMENT_PENDING.value, OrderStatus.CREATED.value}:
        log.info("order not awaiting payment; skipping", order=order.number, status=order.status)
        return

    order_service.transition(db, order, OrderStatus.PAID, reason="Verified payment", actor_type="WEBHOOK", commit=False)

    revenue_service.record_verified_payment(
        db, payment, service_fee_amount=to_money(order.service_fee), order=order, commit=False
    )

    user = db.get(User, order.user_id)
    score, level = fraud_service.assess_and_store_order(db, order)

    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        order_service.transition(
            db, order, OrderStatus.MANUAL_REVIEW, reason=f"Risk score {score} ({level.value})", actor_type="SYSTEM", commit=False
        )
        if user:
            notification_service.notify_event(db, user, "order_review", {"number": order.number}, link=f"/dashboard/orders/{order.id}", commit=False)
        _notify_admins_fraud(db, order, score, level)
    else:
        order_service.transition(db, order, OrderStatus.PROCESSING, reason="Queued for delivery", actor_type="SYSTEM", commit=False)
        for item in order.items:
            Queue(QueueName.SUPPLIER_ORDERS.value).enqueue(
                "deliver_order_item",
                {"order_id": order.id, "order_item_id": item.id},
                dedupe_key=f"deliver:{item.id}",
            )
        if user:
            notification_service.notify_event(
                db, user, "payment_success",
                {"amount": f"{order.total} {order.currency}", "number": order.number},
                link=f"/dashboard/orders/{order.id}", commit=False,
            )
            notification_service.notify_event(db, user, "order_processing", {"number": order.number}, link=f"/dashboard/orders/{order.id}", commit=False)


def _notify_admins_fraud(db: DbSession, order: Order, score: int, level: RiskLevel) -> None:
    from vyron.db.models import Notification
    from vyron.enums import ADMIN_ROLES

    admins = db.query(User).filter(User.role.in_([r.value for r in ADMIN_ROLES])).all()
    for admin in admins:
        db.add(
            Notification(
                user_id=admin.id,
                type="SECURITY",
                title=f"High-risk order {order.number} ({level.value}, score {score})",
                body="Order moved to MANUAL_REVIEW by the fraud engine.",
                link="/admin/orders?status=MANUAL_REVIEW",
                data={"order_id": order.id, "score": score, "level": level.value},
            )
        )
    db.flush()


def mark_failed(db: DbSession, payment: Payment, reason: str = "") -> None:
    if payment.status in {PaymentStatus.PAID.value, PaymentStatus.REFUNDED.value}:
        return
    payment.status = PaymentStatus.FAILED.value
    payment.failure_reason = reason[:500]
    db.flush()
    if payment.order_id:
        order = db.get(Order, payment.order_id)
        user = db.get(User, order.user_id) if order else None
        if user and order:
            notification_service.notify_event(db, user, "payment_failed", {"number": order.number}, link=f"/dashboard/orders/{order.id}", commit=False)
    audit_service.record_audit(
        db, "payment.failed", actor_type="WEBHOOK", entity_type="payment", entity_id=payment.id,
        after={"reason": reason[:200]}, commit=False,
    )
    db.commit()


def _handle_provider_refund(db: DbSession, payment: Payment, event) -> None:
    amount = to_money(event.amount) if event.amount is not None else to_money(payment.amount)
    refund = (
        db.query(Refund)
        .filter(Refund.payment_id == payment.id, Refund.status.in_([RefundStatus.PENDING.value, RefundStatus.PROCESSING.value]))
        .first()
    )
    if refund is None:
        refund = Refund(
            payment_id=payment.id,
            order_id=payment.order_id,
            amount=amount,
            currency=payment.currency,
            reason="Provider-side refund",
            status=RefundStatus.COMPLETED.value,
            provider_refund_id=event.provider_payment_id,
        )
        db.add(refund)
    else:
        refund.status = RefundStatus.COMPLETED.value
    db.flush()
    _apply_refund_effects(db, refund, payment)


def complete_refund(db: DbSession, refund: Refund, admin: User) -> Refund:
    payment = db.get(Payment, refund.payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if refund.status == RefundStatus.COMPLETED.value:
        return refund
    provider = get_provider(payment.provider)
    if provider.is_configured():
        result = provider.refund_payment(
            payment.provider_payment_id or payment.id,
            to_money(refund.amount),
            refund.reason or "refund",
            idempotency_key=f"refund-{refund.id}",
        )
        refund.provider_refund_id = result.provider_refund_id
        if result.status == "FAILED":
            refund.status = RefundStatus.FAILED.value
            db.commit()
            raise PaymentError("Provider rejected the refund.", code="REFUND_FAILED")
    else:
        # No provider configured → cannot move money. Stay honest: mark for manual processing.
        refund.status = RefundStatus.PROCESSING.value
        db.commit()
        raise PaymentError(
            "Provider is not configured — refund recorded and requires manual processing.",
            code="PAYMENT_PROVIDER_NOT_CONFIGURED",
        )
    refund.status = RefundStatus.COMPLETED.value
    db.flush()
    _apply_refund_effects(db, refund, payment)
    audit_service.record_admin_action(db, admin, "refund.completed", target_type="refund", target_id=refund.id, reason=refund.reason, commit=False)
    db.commit()
    return refund


def _apply_refund_effects(db: DbSession, refund: Refund, payment: Payment) -> None:
    payment.refunded_amount = to_money(Decimal(str(payment.refunded_amount or 0)) + to_money(refund.amount))
    payment.status = (
        PaymentStatus.REFUNDED.value
        if payment.refunded_amount >= to_money(payment.amount)
        else PaymentStatus.PARTIALLY_REFUNDED.value
    )
    db.add(
        Transaction(
            type=TransactionType.REFUND_OUT.value,
            amount=to_money(-refund.amount),
            currency=refund.currency,
            payment_id=payment.id,
            order_id=refund.order_id,
            user_id=payment.user_id,
            description="Refund issued",
            idempotency_key=f"tx:refund:{refund.id}",
        )
    )
    revenue_service.record_refund(db, refund)
    if refund.order_id:
        order = db.get(Order, refund.order_id)
        if order and order.status == OrderStatus.REFUND_PENDING.value:
            order_service.transition(db, order, OrderStatus.REFUNDED, reason="Refund completed", actor_type="SYSTEM", commit=False)
        user = db.get(User, order.user_id) if order else None
        if user and order:
            notification_service.notify_event(
                db, user, "refund_issued",
                {"amount": f"{refund.amount} {refund.currency}", "number": order.number},
                link=f"/dashboard/orders/{order.id}", commit=False,
            )
    db.flush()


def request_order_refund(db: DbSession, order: Order, user: User, reason: str) -> Refund:
    payment = (
        db.query(Payment)
        .filter(Payment.order_id == order.id, Payment.status == PaymentStatus.PAID.value)
        .order_by(Payment.paid_at.desc())
        .first()
    )
    if payment is None:
        raise ValidationError("This order has no successful payment to refund.", code="NO_PAYMENT")
    order_service.transition(db, order, OrderStatus.REFUND_PENDING, reason=f"Refund requested: {reason[:200]}", actor_type="USER", actor_id=user.id, commit=False)
    refund = Refund(
        payment_id=payment.id,
        order_id=order.id,
        amount=to_money(order.total),
        currency=order.currency,
        reason=reason[:500],
        status=RefundStatus.PENDING.value,
        requested_by_user_id=user.id,
        idempotency_key=f"refund:order:{order.id}",
    )
    db.add(refund)
    db.commit()
    audit_service.record_audit(db, "refund.requested", actor_id=user.id, actor_type="USER", entity_type="order", entity_id=order.id)
    return refund


# --- reconciliation --------------------------------------------------------------------------
def reconcile_stale_payments(db: DbSession, limit: int = 50) -> int:
    """Worker task: verify PENDING payments older than threshold directly with the provider.

    This is how missed webhooks are recovered — with the provider as the source
    of truth (never guessing).
    """
    from datetime import timedelta

    cutoff = utcnow() - timedelta(minutes=PENDING_RECONCILE_MINUTES)
    stale = (
        db.query(Payment)
        .filter(Payment.status.in_([PaymentStatus.PENDING.value, PaymentStatus.PROCESSING.value]), Payment.created_at < cutoff)
        .order_by(Payment.created_at.asc())
        .limit(limit)
        .all()
    )
    handled = 0
    for payment in stale:
        try:
            provider = get_provider(payment.provider)
            if not provider.is_configured() or not payment.provider_payment_id:
                continue
            result = provider.verify_payment(payment.provider_payment_id)
            if result.status == "PAID":
                mark_paid(db, payment, source="reconciliation")
                handled += 1
            elif result.status in {"FAILED", "CANCELLED", "EXPIRED"}:
                mark_failed(db, payment, reason=f"reconciliation: {result.status}")
                handled += 1
        except Exception as exc:
            db.rollback()
            log.warning(f"reconciliation failed for payment {payment.id}: {exc}")
    return handled


def verify_payment_status(db: DbSession, payment_id: str) -> Payment:
    """Used by return pages: server-side confirmation via provider API."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.status != PaymentStatus.PAID.value:
        try:
            provider = get_provider(payment.provider)
            if provider.is_configured() and payment.provider_payment_id:
                result = provider.verify_payment(payment.provider_payment_id)
                if result.status == "PAID":
                    mark_paid(db, payment, source="verify")
                elif result.status in {"FAILED", "CANCELLED", "EXPIRED"}:
                    mark_failed(db, payment, reason=f"verify: {result.status}")
        except Exception as exc:
            log.warning(f"verify_payment_status error: {exc}")
            db.rollback()
    db.refresh(payment)
    return payment


def available_providers(db: DbSession) -> list:
    """Providers usable at checkout right now (configured only)."""
    from vyron.payments.registry import provider_status

    return [p for p in provider_status() if p["configured"]]


def approve_refund(db: DbSession, refund, admin) -> Refund:
    """Approve a pending refund request → execute via provider (or flag manual)."""
    if refund.status != RefundStatus.PENDING.value:
        raise ValidationError("Only pending refunds can be approved.", code="INVALID_STATE")
    refund.processed_by_user_id = admin.id
    db.commit()
    return complete_refund(db, refund, admin)


def reject_refund(db: DbSession, refund, admin, reason: str) -> Refund:
    if refund.status != RefundStatus.PENDING.value:
        raise ValidationError("Only pending refunds can be rejected.", code="INVALID_STATE")
    refund.status = RefundStatus.REJECTED.value
    refund.processed_by_user_id = admin.id
    refund.reason = ((refund.reason or "") + f" | Rejected: {reason}"[:300])[:500]
    if refund.order_id:
        order = db.get(Order, refund.order_id)
        if order and order.status == OrderStatus.REFUND_PENDING.value:
            order_service.transition(
                db, order, OrderStatus.COMPLETED, reason=f"Refund rejected: {reason[:120]}", actor_type="ADMIN", actor_id=admin.id, commit=False
            )
    audit_service.record_admin_action(db, admin, "refund.rejected", target_type="refund", target_id=refund.id, reason=reason, commit=False)
    db.commit()
    return refund
