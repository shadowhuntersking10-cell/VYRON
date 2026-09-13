"""Order lifecycle: create (server-side totals) -> pay -> supplier -> complete."""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.services import coupon as coupon_svc
from app.services import ledger, notify
from app.services.pricing import q
from app.utils.logging import get_logger
from app.utils.security import new_token

log = get_logger("vyron.orders")

VALID_TRANSITIONS = {
    "PENDING_PAYMENT": {"PAID", "CANCELLED", "FAILED"},
    "PAID": {"PROCESSING", "MANUAL_REVIEW", "REFUND_PENDING", "CANCELLED"},
    "PROCESSING": {"SUPPLIER_PROCESSING", "MANUAL_REVIEW", "COMPLETED", "FAILED"},
    "SUPPLIER_PROCESSING": {"COMPLETED", "FAILED", "MANUAL_REVIEW"},
    "MANUAL_REVIEW": {"PROCESSING", "COMPLETED", "FAILED", "REFUND_PENDING", "CANCELLED"},
    "FAILED": {"MANUAL_REVIEW", "REFUND_PENDING"},
    "REFUND_PENDING": {"REFUNDED", "MANUAL_REVIEW"},
    "COMPLETED": set(),
    "CANCELLED": set(),
    "REFUNDED": set(),
}


class OrderError(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__(key)


def _timeline(order: models.Order) -> list:
    try:
        return json.loads(order.timeline or "[]")
    except Exception:
        return []


def push_timeline(order: models.Order, event: str, note: str = "") -> None:
    events = _timeline(order)
    events.append({"event": event, "note": note, "at": dt.datetime.utcnow().isoformat()})
    order.timeline = json.dumps(events)


def set_status(order: models.Order, new_status: str, note: str = "") -> None:
    allowed = VALID_TRANSITIONS.get(order.status, set())
    if new_status != order.status and new_status not in allowed:
        raise OrderError(f"invalid_transition:{order.status}->{new_status}")
    order.status = new_status
    push_timeline(order, new_status, note)


def public_id() -> str:
    return "VY-" + new_token(6).replace("-", "").replace("_", "").upper()[:8]


def create_order(db: Session, user: models.User | None, items: list[dict], coupon_code: str = "",
                 customer_fields: dict | None = None, idempotency_key: str = "",
                 kind: str = "topup") -> models.Order:
    if not settings.SALES_ENABLED:
        raise OrderError("sales_disabled")
    if not items:
        raise OrderError("empty_cart")
    idempotency_key = idempotency_key or new_token(24)
    existing = db.query(models.Order).filter_by(idempotency_key=idempotency_key).first()
    if existing:
        return existing  # idempotent

    subtotal = Decimal("0")
    game_id = None
    product_id = None
    prepared: list[dict] = []
    for it in items:
        qty = max(1, int(it.get("quantity") or 1))
        if it.get("product_id"):
            product = db.get(models.Product, int(it["product_id"]))
            if not product or product.status != "active":
                raise OrderError("product_unavailable")
            variant = None
            unit = q(product.customer_price)
            if it.get("variant_id"):
                variant = db.get(models.ProductVariant, int(it["variant_id"]))
                if not variant or variant.product_id != product.id:
                    raise OrderError("product_unavailable")
                unit = (unit + q(variant.price_delta)).quantize(Decimal("0.01"))
            game_id = product.game_id
            product_id = product.id
            prepared.append({"product": product, "variant": variant, "listing": None,
                             "title": product.name, "qty": qty, "unit": unit})
            subtotal += unit * qty
        elif it.get("listing_id"):
            listing = db.get(models.MarketplaceListing, int(it["listing_id"]))
            if not listing or listing.status != "active" or listing.stock < qty:
                raise OrderError("listing_unavailable")
            unit = q(listing.price)
            prepared.append({"product": None, "variant": None, "listing": listing,
                             "title": listing.title, "qty": qty, "unit": unit})
            subtotal += unit * qty
        else:
            raise OrderError("invalid_item")

    coupon, discount, err = coupon_svc.validate(
        db, coupon_code, user.id if user else None, subtotal, game_id, product_id)
    if err:
        raise OrderError(err)

    service_fee = Decimal("0")
    payment_fee = Decimal("0")
    total = (subtotal - discount + service_fee + payment_fee).quantize(Decimal("0.01"))
    if total < 0:
        total = Decimal("0")

    order = models.Order(
        public_id=public_id(), user_id=user.id if user else None, kind=kind,
        status="PENDING_PAYMENT", currency=settings.DEFAULT_CURRENCY,
        subtotal=subtotal, discount=discount, service_fee=service_fee,
        payment_fee=payment_fee, total=total, idempotency_key=idempotency_key,
        coupon_code=coupon.code if coupon else "",
        customer_fields=json.dumps(customer_fields or {}),
    )
    db.add(order)
    db.flush()
    for p in prepared:
        db.add(models.OrderItem(
            order_id=order.id,
            product_id=p["product"].id if p["product"] else None,
            variant_id=p["variant"].id if p["variant"] else None,
            listing_id=p["listing"].id if p["listing"] else None,
            title=p["title"], quantity=p["qty"], unit_price=p["unit"],
            total_price=(p["unit"] * p["qty"]).quantize(Decimal("0.01")),
        ))
        if p["listing"]:
            p["listing"].stock = max(0, p["listing"].stock - p["qty"])
    if coupon and user:
        coupon_svc.consume(db, coupon, user.id, order.id, discount)
    push_timeline(order, "CREATED", f"total={total}")
    db.commit()
    log.info("order created id=%s public=%s total=%s", order.id, order.public_id, total)
    if user:
        notify.create(db, user.id, "order_created", "order_created", order.public_id, f"/orders/{order.public_id}")
        db.commit()
    return order


def mark_paid(db: Session, order: models.Order, provider: str, external_id: str = "") -> None:
    """Called ONLY after verified server-side payment confirmation."""
    if order.status != "PENDING_PAYMENT":
        return  # idempotent
    set_status(order, "PAID", f"provider={provider} ext={external_id}")
    # ledger: gross sale + payment fee estimate
    fee_pct = q(settings.PAYMENT_FEE_PERCENT) / 100
    fee = (q(order.total) * fee_pct + q(settings.PAYMENT_FEE_FIXED)).quantize(Decimal("0.01"))
    order.payment_fee = fee
    ledger.record(db, "gross_sale", order.total, order.id, order.currency, f"order {order.public_id}")
    ledger.record(db, "payment_fee", -fee, order.id, order.currency, provider)
    db.flush()
    log.info("order PAID id=%s via %s", order.id, provider)
    # route to fulfillment
    if order.kind == "marketplace":
        fulfill_marketplace(db, order)
    elif order.kind == "donation":
        fulfill_donation(db, order)
    elif order.kind == "wallet":
        fulfill_wallet_topup(db, order)
    else:
        fulfill_topup(db, order)
    if order.user_id:
        notify.create(db, order.user_id, "payment_confirmed", "payment_confirmed",
                      order.public_id, f"/orders/{order.public_id}")
    db.commit()


def fulfill_topup(db: Session, order: models.Order) -> None:
    from app.suppliers import get_adapter  # lazy to avoid cycles

    set_status(order, "PROCESSING", "fulfillment started")
    if not settings.SUPPLIER_ORDERS_ENABLED:
        set_status(order, "MANUAL_REVIEW", "supplier orders disabled")
        db.flush()
        return
    # find supplier from first product item
    supplier = None
    for item in order.items:
        if item.product_id:
            product = db.get(models.Product, item.product_id)
            if product and product.supplier_id:
                supplier = db.get(models.Supplier, product.supplier_id)
                break
    adapter = get_adapter(supplier)
    if adapter is None or not adapter.is_configured():
        set_status(order, "MANUAL_REVIEW", "supplier not configured")
        db.flush()
        log.warning("order %s -> MANUAL_REVIEW (no supplier)", order.id)
        return
    # duplicate protection: unique reference per order
    reference = f"VYRON-{order.id}-{order.public_id}"
    existing = db.query(models.SupplierOrder).filter_by(reference=reference).first()
    if existing:
        log.warning("duplicate supplier order blocked ref=%s", reference)
        return
    try:
        fields = json.loads(order.customer_fields or "{}")
    except Exception:
        fields = {}
    sup_order = models.SupplierOrder(
        supplier_id=supplier.id, order_id=order.id, reference=reference, status="created",
        payload=json.dumps({"items": [{"title": i.title, "qty": i.quantity} for i in order.items],
                            "fields": fields}),
    )
    db.add(sup_order)
    db.flush()
    try:
        result = adapter.create_order(reference, sup_order.payload)
        sup_order.external_order_id = str(result.get("external_id", ""))
        sup_order.response = json.dumps(result)[:4000]
        sup_order.status = "submitted"
        set_status(order, "SUPPLIER_PROCESSING", f"supplier={supplier.code}")
        db.flush()
        log.info("supplier order submitted ref=%s", reference)
    except Exception as exc:  # noqa: BLE001
        sup_order.status = "failed"
        sup_order.last_error = str(exc)[:500]
        set_status(order, "MANUAL_REVIEW", f"supplier error: {exc}")
        db.flush()
        log.error("supplier order failed ref=%s err=%s", reference, exc)


def fulfill_marketplace(db: Session, order: models.Order) -> None:
    from app.services import marketplace_svc as ms

    set_status(order, "PROCESSING", "marketplace fulfillment")
    for item in order.items:
        if not item.listing_id:
            continue
        listing = db.get(models.MarketplaceListing, item.listing_id)
        if not listing:
            continue
        seller = db.get(models.Seller, listing.seller_id)
        category = db.get(models.MarketplaceCategory, listing.category_id) if listing.category_id else None
        pct = ms.commission_percent(db, seller, category, settings.MARKETPLACE_COMMISSION_PERCENT)
        commission, net = ms.split_sale(item.total_price, pct)
        ledger.record(db, "marketplace_commission", commission, order.id, order.currency,
                      f"seller={seller.id if seller else '?'}")
        if seller:
            ms.credit_sale(db, seller.id, net)
            seller.sales_count = (seller.sales_count or 0) + item.quantity
        listing.sales_count = (listing.sales_count or 0) + item.quantity
    set_status(order, "COMPLETED", "digital delivery / seller notified")
    db.flush()


def fulfill_donation(db: Session, order: models.Order) -> None:
    donation = db.query(models.Donation).filter_by(order_id=order.id).first()
    if not donation:
        set_status(order, "MANUAL_REVIEW", "donation record missing")
        db.flush()
        return
    fee_pct = q(settings.DONATION_FEE_PERCENT) / 100
    fee = (q(donation.amount) * fee_pct).quantize(Decimal("0.01"))
    donation.platform_fee = fee
    donation.net_amount = (q(donation.amount) - fee).quantize(Decimal("0.01"))
    donation.status = "paid"
    profile = db.get(models.DonationProfile, donation.profile_id)
    if profile:
        profile.raised_amount = q(profile.raised_amount) + donation.net_amount
    ledger.record(db, "donation_fee", fee, order.id, order.currency, f"profile={donation.profile_id}")
    set_status(order, "COMPLETED", "donation credited")
    db.flush()


def fulfill_wallet_topup(db: Session, order: models.Order) -> None:
    from app.services import wallet as wallet_svc

    if order.user_id:
        wallet_svc.deposit(db, order.user_id, order.total, reference=order.public_id)
    set_status(order, "COMPLETED", "wallet credited")
    db.flush()
