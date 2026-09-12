"""Seller marketplace service — profiles, listings, orders, balances, payouts,
promotions and premium subscriptions.

Financial rules:
- commission is CONFIGURABLE (seller override > platform setting), never hardcoded
- earnings enter `pending`, are released to `available` after the holding
  period (worker), and payouts move money inside row-locked transactions with
  idempotent balance transactions — a balance can never be deducted twice
- sensitive delivery payloads are Fernet-encrypted at rest and revealed only
  to the buyer after completion
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import (
    Game,
    ListingPromotion,
    Payment,
    PayoutRequest,
    SellerBalance,
    SellerBalanceTransaction,
    SellerListing,
    SellerOrder,
    SellerProfile,
    SellerSubscription,
    SellerSubscriptionPlan,
    Transaction,
    User,
)
from vyron.enums import (
    BalanceTxType,
    ListingDeliveryType,
    ListingStatus,
    PaymentPurpose,
    PayoutStatus,
    PromotionKind,
    SellerOrderStatus,
    SellerStatus,
    SubscriptionStatus,
    TransactionType,
    UserRole,
)
from vyron.errors import ConflictError, ForbiddenError, InsufficientBalanceError, NotFoundError, ValidationError
from vyron.logging import get_logger
from vyron.money import pct_of, to_money
from vyron.security.crypto import decrypt_str, encrypt_str
from vyron.services import audit_service, notification_service, order_service, revenue_service, settings_service

log = get_logger("vyron.seller")

IMMEDIATE_DELIVERY_TYPES = {
    ListingDeliveryType.INSTANT.value,
    ListingDeliveryType.ACCOUNT.value,
    ListingDeliveryType.GIFT_CARD.value,
    ListingDeliveryType.GAME_KEY.value,
}


# --- profile ------------------------------------------------------------------------------
def become_seller(db: DbSession, user: User, display_name: str, description: Optional[str] = None) -> SellerProfile:
    existing = db.query(SellerProfile).filter(SellerProfile.user_id == user.id).first()
    if existing:
        return existing
    profile = SellerProfile(
        user_id=user.id,
        display_name=(display_name or user.name).strip()[:120],
        description=(description or "").strip()[:2000] or None,
        avatar_url=user.avatar_url,
    )
    db.add(profile)
    db.flush()
    db.add(SellerBalance(seller_id=profile.id))
    if user.role == UserRole.USER.value:
        user.role = UserRole.SELLER.value
    db.commit()
    audit_service.record_audit(db, "seller.created", actor_id=user.id, actor_type="USER", entity_type="seller_profile", entity_id=profile.id)
    return profile


def get_profile(db: DbSession, user: User) -> SellerProfile:
    profile = db.query(SellerProfile).filter(SellerProfile.user_id == user.id).first()
    if profile is None:
        raise NotFoundError("Seller profile not found. Become a seller first.", code="NOT_A_SELLER")
    return profile


def get_balance(db: DbSession, seller_id: str) -> SellerBalance:
    balance = db.query(SellerBalance).filter(SellerBalance.seller_id == seller_id).first()
    if balance is None:
        balance = SellerBalance(seller_id=seller_id)
        db.add(balance)
        db.commit()
    return balance


def update_profile(db: DbSession, profile: SellerProfile, *, display_name: Optional[str] = None, description: Optional[str] = None, avatar_url: Optional[str] = None) -> SellerProfile:
    if display_name is not None:
        profile.display_name = display_name.strip()[:120]
    if description is not None:
        profile.description = description.strip()[:2000] or None
    if avatar_url is not None:
        profile.avatar_url = avatar_url[:500] or None
    db.commit()
    return profile


# --- listings -----------------------------------------------------------------------------
def create_listing(
    db: DbSession,
    profile: SellerProfile,
    *,
    title: str,
    description: Optional[str],
    price: Decimal,
    currency: str = "USD",
    game_id: Optional[str] = None,
    delivery_type: str = ListingDeliveryType.MANUAL.value,
    images: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    sensitive_delivery_data: Optional[str] = None,
    submit_for_review: bool = False,
) -> SellerListing:
    title = (title or "").strip()
    if len(title) < 4:
        raise ValidationError("Title must be at least 4 characters.", code="TITLE_TOO_SHORT")
    price = to_money(price)
    if price <= 0:
        raise ValidationError("Price must be positive.", code="PRICE_INVALID")
    if delivery_type not in {t.value for t in ListingDeliveryType}:
        raise ValidationError("Invalid delivery type.", code="DELIVERY_TYPE_INVALID")
    if game_id and db.get(Game, game_id) is None:
        raise ValidationError("Unknown game.", code="GAME_NOT_FOUND")

    listing = SellerListing(
        seller_id=profile.id,
        game_id=game_id or None,
        title=title[:200],
        description=(description or "").strip()[:4000] or None,
        price=price,
        currency=currency.upper()[:8],
        delivery_type=delivery_type,
        status=ListingStatus.PENDING_REVIEW.value if submit_for_review else ListingStatus.DRAFT.value,
        images=[str(url)[:500] for url in (images or [])][:8],
        metadata_=metadata or {},
        sensitive_delivery_data_enc=encrypt_str(sensitive_delivery_data) if sensitive_delivery_data else None,
    )
    db.add(listing)
    db.commit()
    return listing


def update_listing(db: DbSession, profile: SellerProfile, listing_id: str, **fields: Any) -> SellerListing:
    listing = db.query(SellerListing).filter(SellerListing.id == listing_id, SellerListing.seller_id == profile.id).first()
    if listing is None:
        raise NotFoundError("Listing not found.")
    if listing.status == ListingStatus.SOLD.value:
        raise ConflictError("A sold listing cannot be edited.", code="LISTING_SOLD")
    if "title" in fields and fields["title"]:
        listing.title = str(fields["title"]).strip()[:200]
    if "description" in fields:
        listing.description = (fields["description"] or "").strip()[:4000] or None
    if "price" in fields and fields["price"] is not None:
        price = to_money(fields["price"])
        if price <= 0:
            raise ValidationError("Price must be positive.", code="PRICE_INVALID")
        listing.price = price
    if "game_id" in fields:
        listing.game_id = fields["game_id"] or None
    if "delivery_type" in fields and fields["delivery_type"]:
        listing.delivery_type = fields["delivery_type"]
    if "images" in fields and fields["images"] is not None:
        listing.images = [str(url)[:500] for url in fields["images"]][:8]
    if "sensitive_delivery_data" in fields:
        value = fields["sensitive_delivery_data"]
        listing.sensitive_delivery_data_enc = encrypt_str(value) if value else None
    db.commit()
    return listing


def submit_listing(db: DbSession, profile: SellerProfile, listing_id: str) -> SellerListing:
    listing = db.query(SellerListing).filter(SellerListing.id == listing_id, SellerListing.seller_id == profile.id).first()
    if listing is None:
        raise NotFoundError("Listing not found.")
    if listing.status not in {ListingStatus.DRAFT.value, ListingStatus.REJECTED.value}:
        raise ConflictError("Only drafts or rejected listings can be submitted.", code="INVALID_LISTING_STATE")
    listing.status = ListingStatus.PENDING_REVIEW.value
    listing.rejection_reason = None
    db.commit()
    return listing


def review_listing(db: DbSession, listing: SellerListing, admin: User, approve: bool, reason: Optional[str] = None) -> SellerListing:
    if approve:
        listing.status = ListingStatus.APPROVED.value
        listing.approved_at = utcnow()
        listing.rejection_reason = None
    else:
        listing.status = ListingStatus.REJECTED.value
        listing.rejection_reason = (reason or "")[:400] or None
    db.commit()
    seller_user = db.get(User, listing.seller.user_id) if listing.seller else None
    if seller_user:
        notification_service.notify_event(
            db, seller_user, "listing_reviewed",
            {"title": listing.title, "status": listing.status.replace("_", " ").title()},
            link=f"/seller/listings/{listing.id}",
        )
    audit_service.record_admin_action(db, admin, "listing.reviewed", target_type="listing", target_id=listing.id, reason=reason, data={"approve": approve})
    return listing


def set_listing_status(db: DbSession, listing: SellerListing, admin: User, new_status: str, reason: Optional[str] = None) -> SellerListing:
    if new_status not in {s.value for s in ListingStatus}:
        raise ValidationError("Invalid status.", code="STATUS_INVALID")
    listing.status = new_status
    if new_status == ListingStatus.SUSPENDED.value:
        listing.rejection_reason = (reason or "")[:400] or None
    db.commit()
    audit_service.record_admin_action(db, admin, "listing.status", target_type="listing", target_id=listing.id, reason=reason, data={"status": new_status})
    return listing


def browse_listings(
    db: DbSession,
    *,
    query: Optional[str] = None,
    game_id: Optional[str] = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 24,
) -> Dict[str, Any]:
    q = db.query(SellerListing).filter(SellerListing.status == ListingStatus.APPROVED.value)
    if game_id:
        q = q.filter(SellerListing.game_id == game_id)
    if query:
        like = f"%{query.strip()[:80]}%"
        q = q.filter(or_(SellerListing.title.like(like), SellerListing.description.like(like)))
    total = q.count()
    if sort == "price_asc":
        q = q.order_by(SellerListing.is_promoted.desc(), SellerListing.price.asc())
    elif sort == "price_desc":
        q = q.order_by(SellerListing.is_promoted.desc(), SellerListing.price.desc())
    else:
        q = q.order_by(SellerListing.is_promoted.desc(), SellerListing.created_at.desc())
    listings = q.offset((max(1, page) - 1) * page_size).limit(page_size).all()
    return {"items": listings, "total": total, "page": page, "page_size": page_size}


# --- marketplace orders ------------------------------------------------------------------
def purchase_listing(
    db: DbSession,
    buyer: User,
    listing_id: str,
    *,
    provider_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> tuple[SellerOrder, Payment]:
    listing = db.get(SellerListing, listing_id)
    if listing is None or listing.status != ListingStatus.APPROVED.value:
        raise NotFoundError("This listing is not available.", code="LISTING_NOT_APPROVED")
    profile = db.get(SellerProfile, listing.seller_id)
    if profile is None or profile.status != SellerStatus.ACTIVE.value:
        raise ConflictError("This seller is not active.", code="SELLER_INACTIVE")
    if profile.user_id == buyer.id:
        raise ValidationError("You cannot buy your own listing.", code="SELF_PURCHASE")

    if idempotency_key:
        existing = db.query(SellerOrder).filter(SellerOrder.idempotency_key == idempotency_key).first()
        if existing:
            payment = db.query(Payment).filter(Payment.seller_order_id == existing.id).order_by(Payment.created_at.desc()).first()
            if payment:
                return existing, payment

    commission_pct = profile.commission_override_pct
    if commission_pct is None:
        commission_pct = settings_service.marketplace_commission_pct(db)
    price = to_money(listing.price)
    fee = to_money(pct_of(price, commission_pct))
    earning = to_money(price - fee)

    seller_order = SellerOrder(
        number=order_service.next_order_number(db, prefix="VYM"),
        listing_id=listing.id,
        seller_id=profile.id,
        buyer_id=buyer.id,
        price=price,
        currency=listing.currency,
        commission_pct=to_money(commission_pct),
        platform_fee=fee,
        seller_earning=earning,
        status=SellerOrderStatus.PENDING_PAYMENT.value,
        idempotency_key=idempotency_key,
    )
    db.add(seller_order)
    db.flush()

    from vyron.services import payment_service

    payment = payment_service.create_payment(
        db,
        purpose=PaymentPurpose.MARKETPLACE_ORDER,
        amount=price,
        currency=listing.currency,
        description=f"Marketplace: {listing.title[:120]}",
        user=buyer,
        provider_name=provider_name,
        seller_order=seller_order,
        metadata={"seller_order_id": seller_order.id, "listing_id": listing.id},
    )
    seller_order.payment_id = payment.id
    db.commit()
    return seller_order, payment


def on_marketplace_order_paid(db: DbSession, seller_order: SellerOrder, payment: Payment) -> None:
    """Verified-payment hook: commission accounting + seller balance hold."""
    if seller_order.status != SellerOrderStatus.PENDING_PAYMENT.value:
        return
    seller_order.status = SellerOrderStatus.PAID.value
    seller_order.payment_id = payment.id
    listing = db.get(SellerListing, seller_order.listing_id)
    if listing and listing.status == ListingStatus.APPROVED.value:
        listing.status = ListingStatus.SOLD.value

    profile = db.get(SellerProfile, seller_order.seller_id)
    balance = get_balance(db, seller_order.seller_id)
    holding_hours = settings_service.holding_period_hours(db)
    available_at = utcnow() + timedelta(hours=holding_hours)

    _apply_balance_tx(
        db,
        balance,
        BalanceTxType.HOLD,
        pending_delta=to_money(seller_order.seller_earning),
        reference_type="SELLER_ORDER",
        reference_id=seller_order.id,
        idempotency_key=f"hold:{seller_order.id}",
        note=f"Earnings held for order {seller_order.number}",
        available_at=available_at,
        commit=False,
    )
    balance.lifetime_earnings = to_money(Decimal(str(balance.lifetime_earnings)) + to_money(seller_order.seller_earning))
    db.add(
        Transaction(
            type=TransactionType.SELLER_CREDIT.value,
            amount=to_money(seller_order.seller_earning),
            currency=seller_order.currency,
            payment_id=payment.id,
            seller_profile_id=seller_order.seller_id,
            description=f"Seller earning (held) for {seller_order.number}",
            idempotency_key=f"tx:sellercredit:{seller_order.id}",
        )
    )
    db.add(
        Transaction(
            type=TransactionType.MARKETPLACE_COMMISSION.value,
            amount=to_money(seller_order.platform_fee),
            currency=seller_order.currency,
            payment_id=payment.id,
            seller_profile_id=seller_order.seller_id,
            description=f"Commission ({seller_order.commission_pct}%) on {seller_order.number}",
            idempotency_key=f"tx:commission:{seller_order.id}",
        )
    )
    revenue_service.record_verified_payment(db, payment, seller_order_id=seller_order.id)
    revenue_service.record_marketplace_commission(db, seller_order)

    # Instant-delivery listings with a stored payload complete immediately.
    if listing and listing.delivery_type in IMMEDIATE_DELIVERY_TYPES and listing.sensitive_delivery_data_enc:
        seller_order.status = SellerOrderStatus.COMPLETED.value
        seller_order.delivered_at = utcnow()
        seller_order.completed_at = utcnow()
        if profile:
            profile.completed_orders += 1

    buyer = db.get(User, seller_order.buyer_id)
    if buyer:
        notification_service.notify_event(
            db, buyer, "payment_success",
            {"amount": f"{seller_order.price} {seller_order.currency}", "number": seller_order.number},
            link="/dashboard/orders", commit=False,
        )
    if profile:
        seller_user = db.get(User, profile.user_id)
        if seller_user:
            notification_service.notify_event(
                db, seller_user, "seller_order",
                {"title": listing.title if listing else "", "price": f"{seller_order.price} {seller_order.currency}", "earning": f"{seller_order.seller_earning} {seller_order.currency}"},
                link="/seller/orders", commit=False,
            )
    db.flush()
    log.info("marketplace order paid", number=seller_order.number, earning=str(seller_order.seller_earning))


def mark_delivered(db: DbSession, seller_order: SellerOrder, profile: SellerProfile, note: Optional[str] = None) -> SellerOrder:
    if seller_order.seller_id != profile.id:
        raise ForbiddenError()
    if seller_order.status != SellerOrderStatus.PAID.value:
        raise ConflictError("Only paid orders can be marked delivered.", code="INVALID_STATE")
    seller_order.status = SellerOrderStatus.DELIVERED.value
    seller_order.delivered_at = utcnow()
    seller_order.delivery_note = (note or "")[:1000] or None
    db.commit()
    return seller_order


def complete_seller_order(db: DbSession, seller_order: SellerOrder) -> SellerOrder:
    if seller_order.status == SellerOrderStatus.COMPLETED.value:
        return seller_order
    seller_order.status = SellerOrderStatus.COMPLETED.value
    seller_order.completed_at = utcnow()
    profile = db.get(SellerProfile, seller_order.seller_id)
    if profile:
        profile.completed_orders += 1
    db.commit()
    return seller_order


def delivery_payload_for_buyer(db: DbSession, seller_order: SellerOrder, user: User) -> Optional[str]:
    """Reveal encrypted delivery data ONLY to the buyer AFTER completion."""
    if user.id != seller_order.buyer_id:
        raise ForbiddenError("Only the buyer can view delivery details.")
    if seller_order.status != SellerOrderStatus.COMPLETED.value:
        return None
    listing = db.get(SellerListing, seller_order.listing_id)
    if listing is None or not listing.sensitive_delivery_data_enc:
        return seller_order.delivery_note
    return decrypt_str(listing.sensitive_delivery_data_enc)


# --- balance lifecycle --------------------------------------------------------------------
def _apply_balance_tx(
    db: DbSession,
    balance: SellerBalance,
    tx_type: BalanceTxType,
    *,
    pending_delta: Decimal = Decimal("0.00"),
    available_delta: Decimal = Decimal("0.00"),
    reserved_delta: Decimal = Decimal("0.00"),
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    idempotency_key: str,
    note: Optional[str] = None,
    available_at=None,
    commit: bool = True,
) -> SellerBalanceTransaction:
    existing = db.query(SellerBalanceTransaction).filter(SellerBalanceTransaction.idempotency_key == idempotency_key).first()
    if existing:
        return existing  # idempotent — never double-apply

    locked = db.query(SellerBalance).with_for_update().filter(SellerBalance.id == balance.id).first() or balance
    new_pending = to_money(Decimal(str(locked.pending)) + pending_delta)
    new_available = to_money(Decimal(str(locked.available)) + available_delta)
    new_reserved = to_money(Decimal(str(locked.reserved)) + reserved_delta)
    if new_pending < 0 or new_available < 0 or new_reserved < 0:
        raise InsufficientBalanceError(
            f"Balance operation would produce a negative balance ({tx_type.value}).", code="INSUFFICIENT_BALANCE"
        )
    locked.pending = new_pending
    locked.available = new_available
    locked.reserved = new_reserved
    tx = SellerBalanceTransaction(
        seller_id=locked.seller_id,
        type=tx_type.value,
        pending_delta=to_money(pending_delta),
        available_delta=to_money(available_delta),
        reserved_delta=to_money(reserved_delta),
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        note=(note or "")[:300] or None,
        available_at=available_at,
    )
    db.add(tx)
    if commit:
        db.commit()
    else:
        db.flush()
    return tx


def release_pending_balances(db: DbSession, limit: int = 500) -> int:
    """Worker/scheduler task: move held earnings to available after the holding period."""
    now = utcnow()
    due: List[SellerBalanceTransaction] = (
        db.query(SellerBalanceTransaction)
        .filter(
            SellerBalanceTransaction.type == BalanceTxType.HOLD.value,
            SellerBalanceTransaction.available_at.isnot(None),
            SellerBalanceTransaction.available_at <= now,
        )
        .limit(limit)
        .all()
    )
    released = 0
    for hold in due:
        release_key = f"release:{hold.id}"
        if db.query(SellerBalanceTransaction).filter(SellerBalanceTransaction.idempotency_key == release_key).first():
            continue
        balance = get_balance(db, hold.seller_id)
        amount = to_money(hold.pending_delta)
        try:
            _apply_balance_tx(
                db,
                balance,
                BalanceTxType.RELEASE,
                pending_delta=-amount,
                available_delta=amount,
                reference_type="HOLD_TX",
                reference_id=hold.id,
                idempotency_key=release_key,
                note="Holding period elapsed",
                commit=True,
            )
            released += 1
        except InsufficientBalanceError:
            db.rollback()
            log.warning("release skipped (pending already moved)", hold=hold.id)
    return released


# --- payouts ---------------------------------------------------------------------------------
def request_payout(
    db: DbSession, profile: SellerProfile, *, amount: Decimal, method: str, details: str, idempotency_key: Optional[str] = None
) -> PayoutRequest:
    amount = to_money(amount)
    minimum = settings_service.min_payout_amount(db)
    if amount < minimum:
        raise ValidationError(f"Minimum payout amount is {minimum}.", code="PAYOUT_MIN")
    if not (details or "").strip():
        raise ValidationError("Payout details are required.", code="PAYOUT_DETAILS_REQUIRED")

    if idempotency_key:
        existing = db.query(PayoutRequest).filter(PayoutRequest.idempotency_key == idempotency_key).first()
        if existing:
            return existing

    balance = get_balance(db, profile.id)
    if to_money(balance.available) < amount:
        raise InsufficientBalanceError(f"Available balance is {balance.available}.", code="INSUFFICIENT_BALANCE")

    payout = PayoutRequest(
        seller_id=profile.id,
        amount=amount,
        currency="USD",
        method=(method or "CARD").upper()[:24],
        details_enc=encrypt_str(details.strip()[:500]),
        status=PayoutStatus.PENDING.value,
        idempotency_key=idempotency_key or f"payout:{profile.id}:{utcnow().timestamp()}",
    )
    db.add(payout)
    db.flush()
    _apply_balance_tx(
        db, balance, BalanceTxType.WITHDRAW,
        available_delta=-amount, reserved_delta=amount,
        reference_type="PAYOUT", reference_id=payout.id,
        idempotency_key=f"withdraw:{payout.id}", note="Payout reserved", commit=False,
    )
    db.commit()
    return payout


def review_payout(db: DbSession, payout: PayoutRequest, admin: User, approve: bool, note: Optional[str] = None) -> PayoutRequest:
    if payout.status != PayoutStatus.PENDING.value:
        raise ConflictError("Only pending payouts can be reviewed.", code="INVALID_STATE")
    if approve:
        payout.status = PayoutStatus.APPROVED.value
    else:
        payout.status = PayoutStatus.REJECTED.value
        balance = get_balance(db, payout.seller_id)
        _apply_balance_tx(
            db, balance, BalanceTxType.REVERSAL,
            reserved_delta=-to_money(payout.amount), available_delta=to_money(payout.amount),
            reference_type="PAYOUT", reference_id=payout.id,
            idempotency_key=f"payout-reject:{payout.id}", note="Rejected payout returned to available", commit=False,
        )
    payout.reviewed_by_user_id = admin.id
    payout.review_note = (note or "")[:400] or None
    db.commit()
    _notify_payout(db, payout)
    audit_service.record_admin_action(db, admin, "payout.reviewed", target_type="payout", target_id=payout.id, reason=note, data={"approve": approve})
    return payout


def process_payout(db: DbSession, payout: PayoutRequest, admin: User) -> PayoutRequest:
    if payout.status != PayoutStatus.APPROVED.value:
        raise ConflictError("Only approved payouts can be processed.", code="INVALID_STATE")
    payout.status = PayoutStatus.PROCESSING.value
    db.commit()
    audit_service.record_admin_action(db, admin, "payout.processing", target_type="payout", target_id=payout.id)
    return payout


def complete_payout(db: DbSession, payout: PayoutRequest, admin: User, reference: Optional[str] = None) -> PayoutRequest:
    if payout.status == PayoutStatus.COMPLETED.value:
        return payout
    if payout.status not in {PayoutStatus.APPROVED.value, PayoutStatus.PROCESSING.value}:
        raise ConflictError("Payout cannot be completed from this state.", code="INVALID_STATE")
    payout.status = PayoutStatus.COMPLETED.value
    payout.processed_at = utcnow()
    payout.reference = (reference or "")[:120] or None
    balance = get_balance(db, payout.seller_id)
    amount = to_money(payout.amount)
    _apply_balance_tx(
        db, balance, BalanceTxType.PAYOUT,
        reserved_delta=-amount,
        reference_type="PAYOUT", reference_id=payout.id,
        idempotency_key=f"payout-complete:{payout.id}", note="Payout completed", commit=False,
    )
    balance.lifetime_paid = to_money(Decimal(str(balance.lifetime_paid)) + amount)
    db.add(
        Transaction(
            type=TransactionType.SELLER_PAYOUT.value,
            amount=-amount,
            currency=payout.currency,
            seller_profile_id=payout.seller_id,
            payout_id=payout.id,
            description=f"Payout completed ({payout.method})",
            idempotency_key=f"tx:payout:{payout.id}",
        )
    )
    revenue_service.record_payout(db, payout)
    db.commit()
    _notify_payout(db, payout)
    audit_service.record_admin_action(db, admin, "payout.completed", target_type="payout", target_id=payout.id, data={"reference": reference})
    return payout


def fail_payout(db: DbSession, payout: PayoutRequest, admin: User, reason: str) -> PayoutRequest:
    if payout.status == PayoutStatus.FAILED.value:
        return payout
    payout.status = PayoutStatus.FAILED.value
    payout.review_note = reason[:400]
    balance = get_balance(db, payout.seller_id)
    _apply_balance_tx(
        db, balance, BalanceTxType.REVERSAL,
        reserved_delta=-to_money(payout.amount), available_delta=to_money(payout.amount),
        reference_type="PAYOUT", reference_id=payout.id,
        idempotency_key=f"payout-fail:{payout.id}", note="Failed payout returned to available", commit=False,
    )
    db.commit()
    _notify_payout(db, payout)
    audit_service.record_admin_action(db, admin, "payout.failed", target_type="payout", target_id=payout.id, reason=reason)
    return payout


def _notify_payout(db: DbSession, payout: PayoutRequest) -> None:
    profile = db.get(SellerProfile, payout.seller_id)
    if profile is None:
        return
    user = db.get(User, profile.user_id)
    if user:
        notification_service.notify_event(
            db, user, "payout_status",
            {"amount": f"{payout.amount} {payout.currency}", "status": payout.status.replace("_", " ").title()},
            link="/seller/payouts",
        )


# --- promotions & subscriptions ------------------------------------------------------------------
def purchase_promotion(
    db: DbSession, profile: SellerProfile, listing_id: str, kind: str, *, provider_name: Optional[str] = None
) -> tuple[ListingPromotion, Payment]:
    listing = db.query(SellerListing).filter(SellerListing.id == listing_id, SellerListing.seller_id == profile.id).first()
    if listing is None:
        raise NotFoundError("Listing not found.")
    if listing.status not in {ListingStatus.APPROVED.value}:
        raise ConflictError("Only approved listings can be promoted.", code="LISTING_NOT_APPROVED")
    if kind.upper() not in {k.value for k in PromotionKind}:
        raise ValidationError("Invalid promotion kind.", code="PROMOTION_KIND_INVALID")
    price = settings_service.promotion_price(db, kind)
    days = settings_service.get_int_setting(db, "promotion_default_days", 7)
    promo = ListingPromotion(
        listing_id=listing.id,
        seller_id=profile.id,
        kind=kind.upper(),
        price=to_money(price),
        currency="USD",
        status="PENDING",
        days=days,
    )
    db.add(promo)
    db.flush()
    from vyron.services import payment_service

    payment = payment_service.create_payment(
        db,
        purpose=PaymentPurpose.PROMOTION,
        amount=promo.price,
        currency="USD",
        description=f"Listing promotion ({promo.kind}) — {listing.title[:80]}",
        user=db.get(User, profile.user_id),
        provider_name=provider_name,
        promotion=promo,
        metadata={"promotion_id": promo.id},
    )
    promo.payment_id = payment.id
    db.commit()
    return promo, payment


def activate_promotion(db: DbSession, promo: ListingPromotion, payment: Payment) -> None:
    if promo.status == "ACTIVE":
        return
    promo.status = "ACTIVE"
    promo.starts_at = utcnow()
    promo.ends_at = utcnow() + timedelta(days=max(1, promo.days))
    promo.payment_id = payment.id
    listing = db.get(SellerListing, promo.listing_id)
    if listing:
        listing.is_promoted = True
    db.add(
        Transaction(
            type=TransactionType.PROMOTION_PURCHASE.value,
            amount=to_money(promo.price),
            currency=promo.currency,
            payment_id=payment.id,
            seller_profile_id=promo.seller_id,
            description=f"Promotion {promo.kind}",
            idempotency_key=f"tx:promo:{promo.id}",
        )
    )
    revenue_service.record_promotion_fee(db, promo)
    db.flush()


def subscribe(db: DbSession, profile: SellerProfile, plan_code: str, *, provider_name: Optional[str] = None) -> tuple[SellerSubscription, Payment]:
    plan = db.query(SellerSubscriptionPlan).filter(SellerSubscriptionPlan.code == plan_code, SellerSubscriptionPlan.active.is_(True)).first()
    if plan is None:
        raise NotFoundError("Subscription plan not found.")
    subscription = SellerSubscription(
        seller_id=profile.id,
        plan_id=plan.id,
        status=SubscriptionStatus.PENDING_PAYMENT.value,
        starts_at=utcnow(),
        ends_at=utcnow() + timedelta(days=plan.period_days),
    )
    db.add(subscription)
    db.flush()
    from vyron.services import payment_service

    payment = payment_service.create_payment(
        db,
        purpose=PaymentPurpose.SUBSCRIPTION,
        amount=plan.price,
        currency=plan.currency,
        description=f"Seller subscription: {plan.name}",
        user=db.get(User, profile.user_id),
        provider_name=provider_name,
        subscription=subscription,
        metadata={"subscription_id": subscription.id},
    )
    subscription.payment_id = payment.id
    db.commit()
    return subscription, payment


def activate_subscription(db: DbSession, subscription: SellerSubscription, payment: Payment) -> None:
    if subscription.status == SubscriptionStatus.ACTIVE.value:
        return
    plan = db.get(SellerSubscriptionPlan, subscription.plan_id)
    period_days = plan.period_days if plan else 30
    subscription.status = SubscriptionStatus.ACTIVE.value
    subscription.starts_at = utcnow()
    subscription.ends_at = utcnow() + timedelta(days=period_days)
    subscription.payment_id = payment.id
    db.add(
        Transaction(
            type=TransactionType.SUBSCRIPTION_PURCHASE.value,
            amount=to_money(payment.amount),
            currency=payment.currency,
            payment_id=payment.id,
            seller_profile_id=subscription.seller_id,
            description=f"Subscription {plan.code if plan else ''}",
            idempotency_key=f"tx:sub:{subscription.id}",
        )
    )
    revenue_service.record_subscription_fee(db, subscription, to_money(payment.amount), payment.currency, payment.id)
    db.flush()


def expire_promotions_and_subscriptions(db: DbSession) -> Dict[str, int]:
    now = utcnow()
    expired_promos = (
        db.query(ListingPromotion)
        .filter(ListingPromotion.status == "ACTIVE", ListingPromotion.ends_at.isnot(None), ListingPromotion.ends_at < now)
        .all()
    )
    for promo in expired_promos:
        promo.status = "EXPIRED"
        listing = db.get(SellerListing, promo.listing_id)
        if listing:
            other_active = (
                db.query(ListingPromotion)
                .filter(ListingPromotion.listing_id == listing.id, ListingPromotion.status == "ACTIVE", ListingPromotion.id != promo.id)
                .first()
            )
            if other_active is None:
                listing.is_promoted = False
    expired_subs = (
        db.query(SellerSubscription)
        .filter(SellerSubscription.status == SubscriptionStatus.ACTIVE.value, SellerSubscription.ends_at < now)
        .all()
    )
    for sub in expired_subs:
        sub.status = SubscriptionStatus.EXPIRED.value
    db.commit()
    return {"promotions": len(expired_promos), "subscriptions": len(expired_subs)}
