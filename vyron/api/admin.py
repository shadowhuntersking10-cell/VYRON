"""Admin panel API — every route is role-gated SERVER-SIDE.

Gate map:
- SUPER_ADMIN: settings, suppliers, users/roles, coupons, promotions, telegram
- ADMIN: dashboard, games, products, orders, fraud, notifications, audit
- MODERATOR: listings review, support, fraud triage
- FINANCE: payments, payouts, refunds, revenue, sellers, donations
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy.orm import Session as DbSession

from vyron.api.deps import ok, paginated
from vyron.config import settings
from vyron.db.base import get_db, utcnow
from vyron.db.models import (
    AdminAction,
    AuditLog,
    Coupon,
    Donation,
    FraudEvent,
    Game,
    ListingPromotion,
    Order,
    OrderItem,
    Payment,
    PaymentWebhook,
    PayoutRequest,
    Product,
    Refund,
    SellerListing,
    SellerProfile,
    Supplier,
    SupportTicket,
    TelegramConnection,
    User,
)
from vyron.enums import ListingStatus, OrderStatus
from vyron.errors import NotFoundError, ValidationError
from vyron.security.ratelimit import enforce_rate_limit
from vyron.security.rbac import require_admin, require_finance, require_moderator, require_super_admin
from vyron.services import (
    admin_service,
    audit_service,
    catalog_service,
    coupon_service,
    delivery_service,
    fraud_service,
    order_service,
    payment_service,
    revenue_service,
    seller_service,
    settings_service,
    supplier_admin_service,
    support_service,
)
from vyron.web import serializers as S

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


def _missing(entity: str):
    raise NotFoundError(f"{entity} not found.")


# --- dashboard ----------------------------------------------------------------------------
@router.get("/stats")
def stats(days: int = Query(30, ge=1, le=365), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    return ok(admin_service.dashboard_stats(db, days))


@router.get("/charts")
def charts(days: int = Query(30, ge=1, le=365), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    return ok(admin_service.chart_series(db, days))


@router.get("/queue-health")
def queue_health(admin: User = Depends(require_admin)):
    return ok(admin_service.queue_health())


@router.get("/catalog-counts")
def catalog_counts(db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    return ok(admin_service.catalog_counts(db))


# --- users ----------------------------------------------------------------------------------
@router.get("/users")
def users(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
    q: Optional[str] = Query(None, max_length=60),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data = admin_service.search_users(db, q, role, status, page, page_size)
    return paginated([S.user_admin(u) for u in data["items"]], data["total"], page, page_size)


@router.get("/users/{user_id}")
def user_detail(user_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    data = admin_service.user_detail(db, user_id)
    return ok(
        {
            "user": S.user_admin(data["user"]),
            "orders": [S.order_admin(o) for o in data["orders"]],
            "payments": [S.payment_public(p) for p in data["payments"]],
            "fraud_events": [
                {
                    "id": f.id,
                    "type": f.type,
                    "risk_score": f.risk_score,
                    "level": f.level,
                    "signals": f.signals or [],
                    "description": f.description,
                    "resolved": f.resolved,
                    "created_at": _iso(f.created_at),
                }
                for f in data["fraud_events"]
            ],
            "audit_logs": [
                {"id": a.id, "action": a.action, "entity_type": a.entity_type, "created_at": _iso(a.created_at)}
                for a in data["audit_logs"]
            ],
        }
    )


@router.post("/users/{user_id}/status")
def set_user_status(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    target = db.get(User, user_id) or _missing("User")
    user = admin_service.set_user_status(db, admin, target, str(payload.get("status", "")), payload.get("reason"))
    return ok(S.user_admin(user), message_code="SAVED")


@router.post("/users/{user_id}/role")
def change_role(
    user_id: str,
    payload: Dict[str, Any] = Body(...),
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    target = db.get(User, user_id) or _missing("User")
    user = admin_service.change_user_role(db, admin, target, str(payload.get("role", "")), payload.get("reason"))
    return ok(S.user_admin(user), message_code="SAVED")


# --- games & products --------------------------------------------------------------------------
@router.get("/games")
def games(db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    items = db.query(Game).order_by(Game.sort_order, Game.name).all()
    return ok([S.game_public(g) for g in items])


@router.post("/games")
def create_game(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    game = catalog_service.upsert_game(db, admin, None, payload)
    return ok(S.game_public(game), message_code="SAVED")


@router.put("/games/{game_id}")
def update_game(game_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    game = db.get(Game, game_id) or _missing("Game")
    game = catalog_service.upsert_game(db, admin, game, payload)
    return ok(S.game_public(game), message_code="SAVED")


@router.get("/products")
def products(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
    game_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Product)
    if game_id:
        query = query.filter(Product.game_id == game_id)
    if q:
        query = query.filter(Product.name.like(f"%{q.strip()}%"))
    total = query.count()
    items = query.order_by(Product.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([S.product_admin(p) for p in items], total, page, page_size)


@router.post("/products")
def create_product(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    product = catalog_service.upsert_product(db, admin, None, payload)
    return ok(S.product_admin(product), message_code="SAVED")


@router.put("/products/{product_id}")
def update_product(product_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    product = db.get(Product, product_id) or _missing("Product")
    product = catalog_service.upsert_product(db, admin, product, payload)
    return ok(S.product_admin(product), message_code="SAVED")


# --- orders -------------------------------------------------------------------------------
@router.get("/orders")
def orders(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status.upper())
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(Order.number.like(term) | Order.user.has(User.username.like(term)))
    total = query.count()
    items = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([S.order_admin(o) for o in items], total, page, page_size)


@router.get("/orders/{order_id}")
def order_detail(order_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    order = db.get(Order, order_id) or _missing("Order")
    payments = db.query(Payment).filter(Payment.order_id == order.id).order_by(Payment.created_at.desc()).all()
    refunds = db.query(Refund).filter(Refund.order_id == order.id).all()
    data = S.order_admin(order)
    data["payments"] = [S.payment_public(p) for p in payments]
    data["refunds"] = [
        {"id": r.id, "amount": str(r.amount), "status": r.status, "reason": r.reason, "created_at": _iso(r.created_at), "updated_at": _iso(r.updated_at)}
        for r in refunds
    ]
    data["supplier_orders"] = [
        {
            "id": so.id,
            "item_id": so.order_item_id,
            "supplier": so.supplier.name if so.supplier else None,
            "external_order_id": so.external_order_id,
            "status": so.status,
            "attempts": so.attempts,
            "cost": str(so.cost) if so.cost is not None else None,
            "last_error": so.last_error,
            "submitted_at": _iso(so.submitted_at),
            "completed_at": _iso(so.completed_at),
        }
        for item in order.items
        for so in item.supplier_orders
    ]
    return ok(data)


@router.post("/orders/{order_id}/approve-review")
def approve_review(order_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    order = db.get(Order, order_id) or _missing("Order")
    if order.status != OrderStatus.MANUAL_REVIEW.value:
        raise ValidationError("Order is not in manual review.", code="INVALID_STATE")
    order_service.force_process_from_review(db, order, admin, note=payload.get("note"))
    return ok(S.order_admin(order), message_code="ORDER_APPROVED")


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    order = db.get(Order, order_id) or _missing("Order")
    order_service.cancel_order(db, order, actor_type="ADMIN", actor_id=admin.id, reason=str(payload.get("reason", ""))[:200] or "Cancelled by admin")
    return ok(S.order_admin(order), message_code="ORDER_CANCELLED")


@router.post("/orders/{order_id}/items/{item_id}/retry")
def retry_item(order_id: str, item_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    item = db.query(OrderItem).filter(OrderItem.id == item_id, OrderItem.order_id == order_id).first() or _missing("Item")
    delivery_service.deliver_order_item(db, order_id, item.id)
    audit_service.record_admin_action(db, admin, "order.item_retry", target_type="order_item", target_id=item.id)
    db.refresh(item)
    return ok({"delivery_state": item.delivery_state})


# --- payments & refunds ----------------------------------------------------------------------
@router.get("/payments")
def payments(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    status: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Payment)
    if status:
        query = query.filter(Payment.status == status.upper())
    if provider:
        query = query.filter(Payment.provider == provider)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(Payment.id.like(term) | Payment.provider_payment_id.like(term))
    total = query.count()
    items = query.order_by(Payment.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated([S.payment_public(p) for p in items], total, page, page_size)


@router.get("/webhook-events")
def webhook_events(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    provider: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(PaymentWebhook)
    if provider:
        query = query.filter(PaymentWebhook.provider == provider)
    total = query.count()
    items = query.order_by(PaymentWebhook.received_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [
            {
                "id": e.id,
                "provider": e.provider,
                "event_id": e.event_id,
                "event_type": e.event_type,
                "payment_id": e.payment_id,
                "signature_valid": e.signature_valid,
                "processed": e.processed,
                "processing_error": e.processing_error,
                "received_at": _iso(e.received_at),
                "processed_at": _iso(e.processed_at),
            }
            for e in items
        ],
        total, page, page_size,
    )


@router.get("/refunds")
def refunds(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Refund)
    if status:
        query = query.filter(Refund.status == status.upper())
    total = query.count()
    items = query.order_by(Refund.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [
            {
                "id": r.id,
                "payment_id": r.payment_id,
                "order_id": r.order_id,
                "amount": str(r.amount),
                "currency": r.currency,
                "reason": r.reason,
                "status": r.status,
                "provider_refund_id": r.provider_refund_id,
                "created_at": _iso(r.created_at),
                "updated_at": _iso(r.updated_at),
            }
            for r in items
        ],
        total, page, page_size,
    )


@router.post("/refunds/{refund_id}/approve")
def approve_refund(refund_id: str, request: Request, db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    enforce_rate_limit(request, "refund-approve", "30/minute", user_id=admin.id)
    refund = db.get(Refund, refund_id) or _missing("Refund")
    payment_service.approve_refund(db, refund, admin)
    return ok({"status": refund.status}, message_code="REFUND_APPROVED")


@router.post("/refunds/{refund_id}/reject")
def reject_refund(refund_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    refund = db.get(Refund, refund_id) or _missing("Refund")
    payment_service.reject_refund(db, refund, admin, str(payload.get("reason", ""))[:300])
    return ok({"status": refund.status}, message_code="REFUND_REJECTED")


# --- suppliers ---------------------------------------------------------------------------------
@router.get("/suppliers")
def suppliers(db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    items = db.query(Supplier).order_by(Supplier.priority, Supplier.name).all()
    return ok([S.supplier_admin(s) for s in items])


@router.post("/suppliers")
def create_supplier(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    supplier = supplier_admin_service.upsert_supplier(db, admin, None, payload)
    return ok(S.supplier_admin(supplier), message_code="SAVED")


@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    supplier = db.get(Supplier, supplier_id) or _missing("Supplier")
    supplier = supplier_admin_service.upsert_supplier(db, admin, supplier, payload)
    return ok(S.supplier_admin(supplier), message_code="SAVED")


@router.post("/suppliers/{supplier_id}/toggle")
def toggle_supplier(supplier_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    supplier = db.get(Supplier, supplier_id) or _missing("Supplier")
    supplier.active = not supplier.active
    db.commit()
    audit_service.record_admin_action(db, admin, "supplier.toggled", target_type="supplier", target_id=supplier.id, data={"active": supplier.active})
    return ok(S.supplier_admin(supplier))


@router.post("/suppliers/{supplier_id}/test")
def test_supplier(supplier_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    db.get(Supplier, supplier_id) or _missing("Supplier")
    return ok(delivery_service.test_supplier_connection(db, supplier_id))


@router.post("/suppliers/{supplier_id}/sync-catalog")
def sync_supplier(supplier_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    db.get(Supplier, supplier_id) or _missing("Supplier")
    return ok(delivery_service.sync_supplier_catalog(db, supplier_id, str(payload.get("mode", "products"))))


# --- sellers, listings, payouts -------------------------------------------------------------
@router.get("/sellers")
def sellers(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    q: Optional[str] = Query(None, max_length=60),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(SellerProfile)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(SellerProfile.display_name.like(term) | SellerProfile.user.has(User.username.like(term)))
    total = query.count()
    items = query.order_by(SellerProfile.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [
            {
                **S.seller_public(p),
                "status": p.status,
                "commission_override_pct": str(p.commission_override_pct) if p.commission_override_pct is not None else None,
                "balance": S.balance_public(seller_service.get_balance(db, p.id)),
            }
            for p in items
        ],
        total, page, page_size,
    )


@router.post("/sellers/{seller_id}/commission")
def set_commission(seller_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    profile = db.get(SellerProfile, seller_id) or _missing("Seller")
    value = payload.get("commission_pct")
    if value in (None, ""):
        profile.commission_override_pct = None
    else:
        pct = Decimal(str(value))
        if pct < 0 or pct > 50:
            raise ValidationError("Commission must be 0-50%.", code="COMMISSION_INVALID")
        profile.commission_override_pct = pct
    db.commit()
    audit_service.record_admin_action(db, admin, "seller.commission", target_type="seller_profile", target_id=profile.id, data={"pct": str(profile.commission_override_pct)})
    return ok({"commission_override_pct": str(profile.commission_override_pct) if profile.commission_override_pct is not None else None})


@router.get("/listings/pending")
def pending_listings(db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    items = db.query(SellerListing).filter(SellerListing.status == ListingStatus.PENDING_REVIEW.value).order_by(SellerListing.created_at).all()
    return ok([S.listing_public(l) for l in items])


@router.post("/listings/{listing_id}/review")
def review_listing(listing_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    listing = db.get(SellerListing, listing_id) or _missing("Listing")
    seller_service.review_listing(db, listing, admin, bool(payload.get("approve")), payload.get("reason"))
    return ok(S.listing_public(listing), message_code="SAVED")


@router.post("/listings/{listing_id}/status")
def listing_status(listing_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    listing = db.get(SellerListing, listing_id) or _missing("Listing")
    seller_service.set_listing_status(db, listing, admin, str(payload.get("status", "")), payload.get("reason"))
    return ok(S.listing_public(listing), message_code="SAVED")


@router.get("/payouts")
def payouts(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(PayoutRequest)
    if status:
        query = query.filter(PayoutRequest.status == status.upper())
    total = query.count()
    items = query.order_by(PayoutRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [S.payout_public(p, decrypt_details=True, seller=db.get(SellerProfile, p.seller_id)) for p in items],
        total, page, page_size,
    )


@router.post("/payouts/{payout_id}/approve")
def approve_payout(payout_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    payout = db.get(PayoutRequest, payout_id) or _missing("Payout")
    seller_service.review_payout(db, payout, admin, True, payload.get("note"))
    return ok(S.payout_public(payout), message_code="SAVED")


@router.post("/payouts/{payout_id}/reject")
def reject_payout(payout_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    payout = db.get(PayoutRequest, payout_id) or _missing("Payout")
    seller_service.review_payout(db, payout, admin, False, payload.get("note"))
    return ok(S.payout_public(payout), message_code="SAVED")


@router.post("/payouts/{payout_id}/process")
def process_payout(payout_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    payout = db.get(PayoutRequest, payout_id) or _missing("Payout")
    seller_service.process_payout(db, payout, admin)
    return ok(S.payout_public(payout), message_code="SAVED")


@router.post("/payouts/{payout_id}/complete")
def complete_payout(payout_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    payout = db.get(PayoutRequest, payout_id) or _missing("Payout")
    seller_service.complete_payout(db, payout, admin, payload.get("reference"))
    return ok(S.payout_public(payout), message_code="SAVED")


@router.post("/payouts/{payout_id}/fail")
def fail_payout(payout_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    payout = db.get(PayoutRequest, payout_id) or _missing("Payout")
    seller_service.fail_payout(db, payout, admin, str(payload.get("reason", ""))[:300])
    return ok(S.payout_public(payout), message_code="SAVED")


# --- donations -------------------------------------------------------------------------------
@router.get("/donations")
def donations(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Donation)
    if status:
        query = query.filter(Donation.status == status.upper())
    total = query.count()
    items = query.order_by(Donation.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return paginated(
        [
            {
                **S.donation_public(d),
                "recipient": d.page.user.username if d.page and d.page.user else None,
                "platform_fee": str(d.platform_fee),
            }
            for d in items
        ],
        total, page, page_size,
    )


# --- coupons & promotions -------------------------------------------------------------------
@router.get("/coupons")
def coupons(db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    items = db.query(Coupon).order_by(Coupon.created_at.desc()).all()
    return ok([S.coupon_admin(c) for c in items])


@router.post("/coupons")
def create_coupon(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    coupon = coupon_service.admin_create_coupon(db, admin, payload)
    return ok(S.coupon_admin(coupon), message_code="SAVED")


@router.put("/coupons/{coupon_id}")
def update_coupon(coupon_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    coupon = db.get(Coupon, coupon_id) or _missing("Coupon")
    coupon = coupon_service.admin_update_coupon(db, admin, coupon, payload)
    return ok(S.coupon_admin(coupon), message_code="SAVED")


@router.get("/promotions")
def promotions(db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    items = db.query(ListingPromotion).order_by(ListingPromotion.created_at.desc()).limit(200).all()
    return ok(
        [
            S.promotion_admin(p, listing=db.get(SellerListing, p.listing_id), seller=db.get(SellerProfile, p.seller_id))
            for p in items
        ]
    )


# --- support & fraud ---------------------------------------------------------------------------
@router.get("/tickets")
def tickets(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_moderator),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    data = support_service.list_tickets(db, staff=True, status=status, page=page, page_size=page_size)
    return paginated(
        [
            {
                "id": t.id,
                "number": t.number,
                "subject": t.subject,
                "status": t.status,
                "priority": t.priority,
                "user": t.user.username if t.user else None,
                "last_message_at": _iso(t.last_message_at),
            }
            for t in data["items"]
        ],
        data["total"], page, page_size,
    )


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    ticket = db.get(SupportTicket, ticket_id) or _missing("Ticket")
    return ok(S.ticket_public(ticket, admin.role))


@router.post("/tickets/{ticket_id}/messages")
def ticket_reply(ticket_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    ticket = db.get(SupportTicket, ticket_id) or _missing("Ticket")
    message = support_service.reply_ticket(db, ticket, admin, str(payload.get("body", "")), bool(payload.get("internal", False)))
    return ok({"id": message.id}, message_code="MESSAGE_SENT")


@router.post("/tickets/{ticket_id}/status")
def ticket_status(ticket_id: str, payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_moderator)):
    ticket = db.get(SupportTicket, ticket_id) or _missing("Ticket")
    support_service.set_ticket_status(db, ticket, admin, str(payload.get("status", "")))
    return ok({"status": ticket.status}, message_code="SAVED")


@router.get("/fraud")
def fraud(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
    resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(FraudEvent)
    if resolved is not None:
        query = query.filter(FraudEvent.resolved.is_(resolved))
    total = query.count()
    items = query.order_by(FraudEvent.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    rows = []
    for f in items:
        event_user = db.get(User, f.user_id) if f.user_id else None
        event_order = db.get(Order, f.order_id) if f.order_id else None
        resolver = db.get(User, f.resolved_by) if f.resolved_by else None
        rows.append(
            {
                "id": f.id,
                "type": f.type,
                "risk_score": f.risk_score,
                "level": f.level,
                "signals": f.signals or [],
                "description": f.description,
                "user": event_user.username if event_user else None,
                "order_number": event_order.number if event_order else None,
                "resolved": f.resolved,
                "resolution": f.resolution,
                "resolved_by": resolver.username if resolver else None,
                "resolved_at": _iso(f.resolved_at),
                "created_at": _iso(f.created_at),
            }
        )
    return paginated(rows, total, page, page_size)


@router.post("/fraud/{event_id}/resolve")
def resolve_fraud(event_id: str, payload: Dict[str, Any] = Body(default={}), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    event = db.get(FraudEvent, event_id) or _missing("FraudEvent")
    fraud_service.resolve_event(db, event, admin, str(payload.get("note", ""))[:300])
    return ok({"resolved": True}, message_code="SAVED")


# --- audit & notifications --------------------------------------------------------------------
@router.get("/audit-logs")
def audit_logs(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_admin),
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    source = (source or "all").lower()

    rows = []
    total = 0
    fetch_limit = page * page_size

    if source in ("all", "audit"):
        query = db.query(AuditLog)
        if actor_id:
            query = query.filter(AuditLog.actor_id == actor_id)
        if action:
            query = query.filter(AuditLog.action.like(f"{action.strip()}%"))
        total += query.count()
        for a in query.order_by(AuditLog.created_at.desc()).limit(fetch_limit).all():
            rows.append(
                {
                    "id": a.id,
                    "source": "audit",
                    "action": a.action,
                    "actor_id": a.actor_id,
                    "actor_type": a.actor_type,
                    "actor_role": a.actor_role,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id,
                    "ip_address": a.ip_address,
                    "created_at": _iso(a.created_at),
                    "_sort": a.created_at,
                }
            )

    if source in ("all", "admin"):
        admin_query = db.query(AdminAction)
        if actor_id:
            admin_query = admin_query.filter(AdminAction.admin_id == actor_id)
        if action:
            admin_query = admin_query.filter(AdminAction.action.like(f"{action.strip()}%"))
        total += admin_query.count()
        role_cache: Dict[str, str] = {}
        for x in admin_query.order_by(AdminAction.created_at.desc()).limit(fetch_limit).all():
            if x.admin_id not in role_cache:
                admin_user = db.get(User, x.admin_id)
                role_cache[x.admin_id] = admin_user.role if admin_user else ""
            rows.append(
                {
                    "id": x.id,
                    "source": "admin_action",
                    "action": x.action,
                    "actor_id": x.admin_id,
                    "actor_type": "ADMIN",
                    "actor_role": role_cache[x.admin_id],
                    "entity_type": x.target_type,
                    "entity_id": x.target_id,
                    "ip_address": x.ip_address,
                    "reason": x.reason,
                    "created_at": _iso(x.created_at),
                    "_sort": x.created_at,
                }
            )

    rows.sort(key=lambda r: r["_sort"], reverse=True)
    page_rows = rows[(page - 1) * page_size : page * page_size]
    for r in page_rows:
        r.pop("_sort", None)
    return paginated(page_rows, total, page, page_size)


@router.post("/notifications/broadcast")
def broadcast(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_admin)):
    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    if not title or not body:
        raise ValidationError("Title and body are required.", code="FIELDS_REQUIRED")
    count = admin_service.notify_users(db, admin, title, body, payload.get("user_ids"))
    return ok({"recipients": count}, message_code="NOTIFICATION_SENT")


# --- settings & revenue -------------------------------------------------------------------------
@router.get("/settings")
def get_settings(db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    return ok(settings_service.admin_snapshot(db))


@router.put("/settings")
def put_settings(payload: Dict[str, Any] = Body(...), db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    return ok(settings_service.admin_update(db, admin, payload), message_code="SETTINGS_SAVED")


@router.get("/revenue/summary")
def revenue_summary(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    days: Optional[int] = Query(None, ge=1, le=365),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = admin_service.range_bounds(days, start, end)
    summary = revenue_service.summary(db, start_dt, end_dt)
    streams = revenue_service.by_stream(db, start_dt, end_dt)
    return ok(
        {
            "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
            "summary": {k: str(v) for k, v in summary.items()},
            "streams": streams,
        }
    )


@router.get("/revenue/series")
def revenue_series_api(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    days: Optional[int] = Query(None, ge=1, le=365),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = admin_service.range_bounds(days, start, end)
    return ok(
        {
            "gross": revenue_service.daily_series(db, "GROSS_REVENUE", start_dt, end_dt),
            "margin": revenue_service.daily_series(db, "TOPUP_MARGIN", start_dt, end_dt),
            "net": revenue_service.daily_series(db, "NET_REVENUE", start_dt, end_dt),
        }
    )


@router.get("/revenue/by-game")
def revenue_by_game(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    days: Optional[int] = Query(None, ge=1, le=365),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = admin_service.range_bounds(days, start, end)
    return ok(revenue_service.by_game(db, start_dt, end_dt))


@router.get("/revenue/by-product")
def revenue_by_product(
    db: DbSession = Depends(get_db),
    admin: User = Depends(require_finance),
    days: Optional[int] = Query(None, ge=1, le=365),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    start_dt, end_dt = admin_service.range_bounds(days, start, end)
    return ok(revenue_service.by_product(db, start_dt, end_dt))


@router.get("/revenue/order/{order_id}")
def order_profitability(order_id: str, db: DbSession = Depends(get_db), admin: User = Depends(require_finance)):
    order = db.get(Order, order_id) or _missing("Order")
    return ok(revenue_service.order_profitability(db, order))


# --- telegram --------------------------------------------------------------------------------
@router.get("/telegram/stats")
def telegram_stats(db: DbSession = Depends(get_db), admin: User = Depends(require_super_admin)):
    from sqlalchemy import func

    total = db.query(func.count(TelegramConnection.id)).scalar() or 0
    linked_7d = (
        db.query(func.count(TelegramConnection.id))
        .filter(TelegramConnection.linked_at >= utcnow() - timedelta(days=7))
        .scalar()
        or 0
    )
    return ok(
        {
            "total_connections": total,
            "linked_last_7_days": linked_7d,
            "bot_configured": settings.telegram_configured,
            "admin_ids_configured": len(settings.admin_telegram_id_list),
        }
    )
