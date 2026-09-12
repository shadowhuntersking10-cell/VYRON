"""Order engine — creation, strict state machine, transaction-safe numbering.

Order numbers: VYR-<year>-<000001> allocated from a locked sequence row.
Duplicate protection: client idempotency key with a UNIQUE constraint; a
double-click returns the original order instead of creating a second one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import (
    Cart,
    CartItem,
    Game,
    Order,
    OrderItem,
    OrderSequence,
    OrderStatusHistory,
    Product,
    ProductVariant,
    User,
)
from vyron.enums import OrderStatus
from vyron.errors import NotFoundError, OrderStateError, ValidationError
from vyron.logging import get_logger
from vyron.money import sum_money, to_money
from vyron.services import audit_service, cart_service, coupon_service

log = get_logger("vyron.orders")

# --- strict state machine -----------------------------------------------------------
ALLOWED_TRANSITIONS: Dict[OrderStatus, set] = {
    OrderStatus.CREATED: {OrderStatus.PAYMENT_PENDING, OrderStatus.CANCELLED, OrderStatus.MANUAL_REVIEW, OrderStatus.FAILED},
    OrderStatus.PAYMENT_PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED, OrderStatus.FAILED, OrderStatus.MANUAL_REVIEW},
    OrderStatus.PAID: {OrderStatus.PROCESSING, OrderStatus.MANUAL_REVIEW, OrderStatus.REFUND_PENDING, OrderStatus.FAILED},
    OrderStatus.PROCESSING: {OrderStatus.DELIVERING, OrderStatus.COMPLETED, OrderStatus.MANUAL_REVIEW, OrderStatus.FAILED, OrderStatus.REFUND_PENDING},
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED, OrderStatus.MANUAL_REVIEW, OrderStatus.FAILED, OrderStatus.REFUND_PENDING},
    OrderStatus.MANUAL_REVIEW: {OrderStatus.PROCESSING, OrderStatus.DELIVERING, OrderStatus.COMPLETED, OrderStatus.REFUND_PENDING, OrderStatus.FAILED, OrderStatus.CANCELLED},
    OrderStatus.FAILED: {OrderStatus.REFUND_PENDING, OrderStatus.MANUAL_REVIEW},
    OrderStatus.COMPLETED: {OrderStatus.REFUND_PENDING},
    OrderStatus.REFUND_PENDING: {OrderStatus.REFUNDED, OrderStatus.MANUAL_REVIEW, OrderStatus.COMPLETED},
    OrderStatus.REFUNDED: set(),
    OrderStatus.CANCELLED: set(),
}

TERMINAL_STATUSES = {OrderStatus.COMPLETED, OrderStatus.REFUNDED, OrderStatus.CANCELLED}


def can_transition(from_status: str, to_status: str) -> bool:
    try:
        source = OrderStatus(from_status)
        target = OrderStatus(to_status)
    except ValueError:
        return False
    return target in ALLOWED_TRANSITIONS.get(source, set())


def transition(
    db: DbSession,
    order: Order,
    to_status: OrderStatus | str,
    *,
    reason: Optional[str] = None,
    actor_type: str = "SYSTEM",
    actor_id: Optional[str] = None,
    commit: bool = True,
) -> Order:
    to_status = OrderStatus(to_status) if not isinstance(to_status, OrderStatus) else to_status
    if order.status == to_status.value:
        return order
    if not can_transition(order.status, to_status.value):
        raise OrderStateError(
            f"Transition {order.status} -> {to_status.value} is not allowed for order {order.number}.",
            details={"order": order.number, "from": order.status, "to": to_status.value},
        )
    from_status = order.status
    order.status = to_status.value
    if to_status == OrderStatus.PAID:
        order.paid_at = utcnow()
    if to_status == OrderStatus.COMPLETED:
        order.completed_at = utcnow()
    if to_status == OrderStatus.CANCELLED:
        order.cancelled_at = utcnow()
    if reason:
        order.failure_reason = reason[:1000] if to_status in (OrderStatus.FAILED, OrderStatus.MANUAL_REVIEW) else order.failure_reason
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=from_status,
            to_status=to_status.value,
            reason=(reason or "")[:400] or None,
            actor_type=actor_type,
            actor_id=actor_id,
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
    log.info("order transition", number=order.number, **{"from": from_status, "to": to_status.value})
    return order


def next_order_number(db: DbSession, prefix: str = "VYR") -> str:
    """Transaction-safe sequence (SELECT ... FOR UPDATE). No separate commit."""
    year = utcnow().year
    row: Optional[OrderSequence] = (
        db.query(OrderSequence).with_for_update().filter(OrderSequence.year == year).first()
    )
    if row is None:
        row = OrderSequence(year=year, last_number=0)
        db.add(row)
        db.flush()
        # re-lock after insert
        row = db.query(OrderSequence).with_for_update().filter(OrderSequence.year == year).first()
    row.last_number += 1
    db.flush()
    return f"{prefix}-{year}-{row.last_number:06d}"


def _snapshot_item(
    db: DbSession,
    order: Order,
    variant: ProductVariant,
    quantity: int,
    values: Dict[str, Any],
) -> OrderItem:
    product = db.get(Product, variant.product_id)
    game = db.get(Game, product.game_id) if product and product.game_id else None
    unit_price = to_money(variant.selling_price)
    unit_cost = to_money(variant.cost_price)
    item = OrderItem(
        order_id=order.id,
        variant_id=variant.id,
        product_name=(product.name if product else variant.name)[:200],
        variant_name=variant.name[:160],
        game_name=(game.name if game else None),
        unit_price=unit_price,
        unit_cost=unit_cost,
        quantity=quantity,
        total=to_money(unit_price * quantity),
        currency=variant.currency or order.currency,
        required_field_values=values or {},
    )
    return item


def create_order_from_cart(
    db: DbSession,
    user: User,
    *,
    provider_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    coupon_code: Optional[str] = None,
) -> Order:
    """Create an order from the user's cart. Prices/totals are server-derived."""
    if idempotency_key:
        existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing:
            return existing

    cart: Cart = cart_service.get_or_create_cart(db, user)
    if not cart.items:
        raise ValidationError("Your cart is empty.", code="CART_EMPTY")

    summary = cart_service.calculate(db, user, ignore_coupon=True)
    lines = [line for line in summary["lines"] if line["quantity"] > 0]
    if not lines:
        raise ValidationError("No purchasable items in cart.", code="CART_EMPTY")

    discount = Decimal("0.00")
    coupon = None
    effective_code = (coupon_code or cart.coupon_code or "").strip().upper()
    if effective_code:
        coupon = coupon_service.find_coupon(db, effective_code)
        if coupon is None:
            raise ValidationError("This coupon code is not valid.", code="COUPON_INVALID")
        discount = coupon_service.validate_coupon(
            db, coupon, user, summary["subtotal"], [(line["variant"], line["quantity"]) for line in lines]
        )

    order = Order(
        user_id=user.id,
        status=OrderStatus.CREATED.value,
        currency=summary["currency"],
        subtotal=to_money(summary["subtotal"]),
        discount=to_money(discount),
        service_fee=to_money(summary["service_fee"]),
        total=to_money(sum_money(summary["subtotal"], -discount, summary["service_fee"])),
        supplier_cost_total=to_money(
            sum_money(*[to_money(line["variant"].cost_price) * line["quantity"] for line in lines])
        ),
        coupon_id=coupon.id if coupon else None,
        payment_provider=provider_name,
        idempotency_key=idempotency_key,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:400] or None,
    )
    order.number = next_order_number(db)
    db.add(order)
    db.flush()

    for line in lines:
        variant: ProductVariant = line["variant"]
        item = _snapshot_item(db, order, variant, line["quantity"], line["required_field_values"])
        db.add(item)
        if variant.stock is not None and variant.stock >= 0:
            variant.stock = max(0, variant.stock - line["quantity"])

    if coupon is not None:
        coupon_service.redeem_coupon(db, coupon, user, order.id, discount)

    db.add(
        OrderStatusHistory(order_id=order.id, from_status=None, to_status=OrderStatus.CREATED.value, actor_type="USER", actor_id=user.id)
    )

    # clear the cart
    db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
    cart.coupon_code = None

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
            if existing:
                return existing
        raise
    db.refresh(order)
    audit_service.record_audit(
        db, "order.created", actor_id=user.id, actor_type="USER", actor_role=user.role,
        entity_type="order", entity_id=order.id, after={"number": order.number, "total": str(order.total)},
        ip_address=ip_address, user_agent=user_agent,
    )
    log.info("order created", number=order.number, total=str(order.total), user=user.username)
    return order


def create_direct_order(
    db: DbSession,
    user: User,
    *,
    variant_id: str,
    quantity: int = 1,
    required_field_values: Optional[Dict[str, Any]] = None,
    provider_name: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Order:
    """Buy-now flow (used by web, Mini App and Telegram bot — same service)."""
    if idempotency_key:
        existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
        if existing:
            return existing

    variant = db.get(ProductVariant, variant_id)
    if variant is None or not variant.active:
        raise NotFoundError("This product option is not available.")
    product = db.get(Product, variant.product_id)
    if product is None or not product.active:
        raise NotFoundError("This product is not available.")
    quantity = max(1, min(int(quantity or 1), 99))
    if variant.stock is not None and variant.stock >= 0 and variant.stock < quantity:
        raise ValidationError("Not enough stock for the requested quantity.", code="OUT_OF_STOCK")
    cleaned_values = cart_service.validate_required_fields(product, required_field_values)

    unit_price = to_money(variant.selling_price)
    subtotal = to_money(unit_price * quantity)
    from vyron.services import settings_service

    fee = settings_service.service_fee(db, subtotal)
    order = Order(
        user_id=user.id,
        status=OrderStatus.CREATED.value,
        currency=variant.currency or "USD",
        subtotal=subtotal,
        discount=Decimal("0.00"),
        service_fee=fee,
        total=to_money(sum_money(subtotal, fee)),
        supplier_cost_total=to_money(to_money(variant.cost_price) * quantity),
        payment_provider=provider_name,
        idempotency_key=idempotency_key,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:400] or None,
    )
    order.number = next_order_number(db)
    db.add(order)
    db.flush()
    db.add(_snapshot_item(db, order, variant, quantity, cleaned_values))
    if variant.stock is not None and variant.stock >= 0:
        variant.stock = max(0, variant.stock - quantity)
    db.add(OrderStatusHistory(order_id=order.id, from_status=None, to_status=OrderStatus.CREATED.value, actor_type="USER", actor_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.query(Order).filter(Order.idempotency_key == idempotency_key).first()
            if existing:
                return existing
        raise
    db.refresh(order)
    audit_service.record_audit(
        db, "order.created", actor_id=user.id, actor_type="USER", actor_role=user.role,
        entity_type="order", entity_id=order.id, after={"number": order.number, "total": str(order.total)},
        ip_address=ip_address, user_agent=user_agent,
    )
    return order


def get_user_order(db: DbSession, user: User, order_id: str) -> Order:
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if order is None:
        raise NotFoundError("Order not found.")
    return order


def cancel_order(db: DbSession, order: Order, *, actor_type: str = "USER", actor_id: Optional[str] = None, reason: str = "Cancelled") -> Order:
    if order.status not in {OrderStatus.CREATED.value, OrderStatus.PAYMENT_PENDING.value, OrderStatus.MANUAL_REVIEW.value}:
        raise OrderStateError("Only unpaid orders can be cancelled.", code="INVALID_ORDER_TRANSITION")
    # restore stock for unpaid orders
    for item in order.items:
        if item.variant_id:
            variant = db.get(ProductVariant, item.variant_id)
            if variant and variant.stock is not None and variant.stock >= 0:
                variant.stock += item.quantity
    return transition(db, order, OrderStatus.CANCELLED, reason=reason, actor_type=actor_type, actor_id=actor_id)


def force_process_from_review(db: DbSession, order: Order, admin, note: Optional[str] = None) -> Order:
    """Admin decision: release a MANUAL_REVIEW order into delivery."""
    from vyron.enums import QueueName
    from vyron.queue.engine import Queue

    transition(
        db, order, OrderStatus.PROCESSING,
        reason=f"Approved from manual review{(': ' + note[:160]) if note else ''}",
        actor_type="ADMIN", actor_id=admin.id, commit=False,
    )
    for item in order.items:
        if item.delivery_state not in {"COMPLETED"}:
            Queue(QueueName.SUPPLIER_ORDERS.value).enqueue(
                "deliver_order_item",
                {"order_id": order.id, "order_item_id": item.id},
                dedupe_key=f"deliver:{item.id}",
            )
    audit_service.record_admin_action(
        db, admin, "order.approved_from_review", target_type="order", target_id=order.id, reason=note, commit=False
    )
    db.commit()
    return order
