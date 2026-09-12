"""Automatic delivery service — the supplier engine's orchestration core.

Flow (per order item):
  PAID order -> queue job -> validate recipient -> pick supplier by priority
  -> create supplier order (idempotency key = item+supplier, UNIQUE)
  -> SUCCESS: item delivered -> when all items delivered: order COMPLETED
     + revenue ledger + notifications (email/site/telegram)
  -> PROCESSING: schedule status reconciliation
  -> safe FAILURE: try next supplier, record attempt
  -> UNKNOWN (timeout/transport): STOP. Reconcile first — never blindly
     re-submit and never duplicate a paid digital delivery.
  -> no supplier configured/exhausted: MANUAL_REVIEW (money stays safe).
"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from vyron.db.base import utcnow
from vyron.db.models import (
    Notification,
    Order,
    OrderItem,
    Supplier,
    SupplierOrder,
    SupplierOrderAttempt,
    User,
)
from vyron.enums import ADMIN_ROLES, OrderStatus, QueueName, SupplierAttemptOutcome, SupplierOrderStatus
from vyron.errors import SupplierNotConfiguredError
from vyron.logging import get_logger
from vyron.money import to_money
from vyron.queue.engine import Queue, RetryJob
from vyron.services import audit_service, notification_service, order_service, revenue_service
from vyron.suppliers.base import RecipientValidation, SupplierProviderError
from vyron.suppliers.router import SupplierCandidate, candidates_for_variant

log = get_logger("vyron.delivery")

RECONCILE_WINDOW = timedelta(minutes=2)
MAX_RECONCILE_HOURS = 2


def _open_supplier_orders(db: DbSession, item_id: str) -> List[SupplierOrder]:
    return (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.order_item_id == item_id,
            SupplierOrder.status.in_(
                [
                    SupplierOrderStatus.PENDING.value,
                    SupplierOrderStatus.SUBMITTED.value,
                    SupplierOrderStatus.PROCESSING.value,
                    SupplierOrderStatus.UNKNOWN.value,
                ]
            ),
        )
        .all()
    )


def _tried_supplier_ids(db: DbSession, item_id: str) -> set:
    rows = db.query(SupplierOrder.supplier_id).filter(SupplierOrder.order_item_id == item_id).all()
    return {row[0] for row in rows}


def deliver_order_item(db: DbSession, order_id: str, order_item_id: str) -> None:
    order: Optional[Order] = db.get(Order, order_id)
    if order is None:
        return
    if order.status not in {
        OrderStatus.PAID.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.DELIVERING.value,
        OrderStatus.MANUAL_REVIEW.value,
    }:
        log.info("delivery skipped for order status", number=order.number, status=order.status)
        return
    item: Optional[OrderItem] = db.get(OrderItem, order_item_id)
    if item is None or item.order_id != order.id:
        return
    if item.delivery_state == "COMPLETED":
        _maybe_finalize_order(db, order)
        return

    # An open supplier order exists => reconcile instead of re-submitting.
    open_orders = _open_supplier_orders(db, item.id)
    if open_orders:
        for supplier_order in open_orders:
            Queue(QueueName.SUPPLIER_STATUS.value).enqueue(
                "reconcile_supplier_order",
                {"supplier_order_id": supplier_order.id},
                dedupe_key=f"reconcile:{supplier_order.id}:{int(utcnow().timestamp() // 60)}",
            )
        log.info("open supplier order exists — reconciling instead of re-submitting", item=item.id)
        return

    tried = _tried_supplier_ids(db, item.id)
    candidates: List[SupplierCandidate] = [c for c in candidates_for_variant(db, item.variant_id or "") if c.supplier.id not in tried]

    if not candidates:
        if not tried:
            _no_supplier_available(db, order, item)
        else:
            _exhausted_suppliers(db, order, item)
        return

    for candidate in candidates:
        outcome = _attempt_supplier(db, order, item, candidate)
        if outcome in {"SUCCESS", "PROCESSING", "UNKNOWN", "VALIDATION"}:
            return
        # FAILURE -> continue to next supplier
    _exhausted_suppliers(db, order, item)


def _attempt_supplier(db: DbSession, order: Order, item: OrderItem, candidate: SupplierCandidate) -> str:
    supplier = candidate.supplier
    mapping = candidate.mapping
    provider = candidate.provider
    idempotency_key = f"{item.id}:{supplier.id}"

    # Create the supplier order row FIRST — the UNIQUE idempotency key makes a
    # double submission impossible even under concurrent workers/retries.
    supplier_order = SupplierOrder(
        order_id=order.id,
        order_item_id=item.id,
        supplier_id=supplier.id,
        idempotency_key=idempotency_key,
        status=SupplierOrderStatus.PENDING.value,
        cost=to_money(mapping.supplier_cost),
        currency=mapping.currency or order.currency,
        recipient_payload=item.required_field_values or {},
    )
    db.add(supplier_order)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        log.info("supplier order already exists (idempotent skip)", item=item.id, supplier=supplier.slug)
        return "FAILURE"

    if order.status == OrderStatus.PROCESSING.value:
        order_service.transition(db, order, OrderStatus.DELIVERING, reason=f"Delivering via {supplier.name}", commit=False)
    item.delivery_state = "DELIVERING"

    attempt = SupplierOrderAttempt(supplier_order_id=supplier_order.id, attempt_no=supplier_order.attempts + 1, action="CREATE")
    db.add(attempt)

    started = utcnow()
    try:
        validation: RecipientValidation = provider.validate_recipient(mapping.external_product_id, item.required_field_values or {})
        if not validation.valid:
            attempt.outcome = SupplierAttemptOutcome.VALIDATION_ERROR.value
            attempt.error = validation.reason[:500]
            supplier_order.status = SupplierOrderStatus.FAILED.value
            supplier_order.last_error = f"recipient invalid: {validation.reason[:300]}"
            supplier_order.completed_at = utcnow()
            db.commit()
            _recipient_invalid(db, order, item, validation.reason)
            return "VALIDATION"

        result = provider.create_order(
            external_product_id=mapping.external_product_id,
            fields=item.required_field_values or {},
            quantity=item.quantity,
            idempotency_key=idempotency_key,
        )
        attempt.duration_ms = int((utcnow() - started).total_seconds() * 1000)
        supplier_order.attempts += 1
        supplier_order.external_order_id = result.external_order_id
        supplier_order.submitted_at = utcnow()

        if result.status == "SUCCESS":
            attempt.outcome = SupplierAttemptOutcome.SUCCESS.value
            supplier_order.status = SupplierOrderStatus.SUCCESS.value
            supplier_order.completed_at = utcnow()
            item.delivery_state = "COMPLETED"
            supplier.balance = None if supplier.balance is None else supplier.balance  # refreshed by sync worker
            db.commit()
            log.info("supplier delivery SUCCESS", order=order.number, supplier=supplier.slug)
            _maybe_finalize_order(db, order)
            return "SUCCESS"

        if result.status == "PROCESSING":
            attempt.outcome = SupplierAttemptOutcome.SUCCESS.value  # accepted, pending
            supplier_order.status = SupplierOrderStatus.PROCESSING.value
            supplier_order.reconcile_after = utcnow() + RECONCILE_WINDOW
            db.commit()
            Queue(QueueName.SUPPLIER_STATUS.value).enqueue(
                "reconcile_supplier_order", {"supplier_order_id": supplier_order.id}, dedupe_key=f"reconcile:{supplier_order.id}:0"
            )
            log.info("supplier delivery PROCESSING", order=order.number, supplier=supplier.slug)
            return "PROCESSING"

        # FAILED
        attempt.outcome = SupplierAttemptOutcome.FAILURE.value
        attempt.error = (result.error or "")[:500]
        supplier_order.status = SupplierOrderStatus.FAILED.value
        supplier_order.last_error = (result.error or "")[:500]
        supplier_order.completed_at = utcnow()
        db.commit()
        log.warning("supplier delivery FAILED, trying next", order=order.number, supplier=supplier.slug, error=result.error)
        return "FAILURE"

    except SupplierNotConfiguredError as exc:
        attempt.outcome = SupplierAttemptOutcome.NOT_CONFIGURED.value
        attempt.error = str(exc)[:500]
        supplier_order.status = SupplierOrderStatus.FAILED.value
        supplier_order.last_error = str(exc)[:500]
        db.commit()
        log.warning("supplier not configured", supplier=supplier.slug)
        return "FAILURE"

    except SupplierProviderError as exc:
        # UNKNOWN outcome — the order MAY exist at the supplier. Never re-submit
        # blindly: reconcile first with the SAME idempotency key.
        attempt.outcome = SupplierAttemptOutcome.TIMEOUT.value if "timeout" in str(exc).lower() else SupplierAttemptOutcome.UNKNOWN.value
        attempt.error = str(exc)[:500]
        supplier_order.status = SupplierOrderStatus.UNKNOWN.value
        supplier_order.last_error = str(exc)[:500]
        supplier_order.reconcile_after = utcnow() + timedelta(seconds=45)
        db.commit()
        Queue(QueueName.SUPPLIER_STATUS.value).enqueue(
            "reconcile_supplier_order", {"supplier_order_id": supplier_order.id}, dedupe_key=f"reconcile:{supplier_order.id}:u0"
        )
        log.error("supplier delivery UNKNOWN — reconciliation scheduled (no blind retry)", order=order.number, supplier=supplier.slug)
        return "UNKNOWN"

    except Exception as exc:
        db.rollback()
        attempt.outcome = SupplierAttemptOutcome.FAILURE.value
        attempt.error = str(exc)[:500]
        supplier_order.status = SupplierOrderStatus.FAILED.value
        supplier_order.last_error = str(exc)[:500]
        db.commit()
        log.exception(f"unexpected supplier error for {supplier.slug}")
        return "FAILURE"


def reconcile_supplier_order(db: DbSession, supplier_order_id: str) -> None:
    supplier_order: Optional[SupplierOrder] = db.get(SupplierOrder, supplier_order_id)
    if supplier_order is None:
        return
    if supplier_order.status in {
        SupplierOrderStatus.SUCCESS.value,
        SupplierOrderStatus.FAILED.value,
        SupplierOrderStatus.CANCELLED.value,
        SupplierOrderStatus.REFUNDED.value,
    }:
        return
    if supplier_order.reconcile_after and supplier_order.reconcile_after > utcnow():
        raise RetryJob("reconcile window not reached", delay_seconds=max(10.0, (supplier_order.reconcile_after - utcnow()).total_seconds()))

    order = db.get(Order, supplier_order.order_id)
    item = db.get(OrderItem, supplier_order.order_item_id)
    if order is None or item is None:
        return
    if order.status in {OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value, OrderStatus.REFUND_PENDING.value}:
        supplier_order.status = SupplierOrderStatus.CANCELLED.value
        db.commit()
        return

    from vyron.suppliers.router import build_provider

    supplier: Optional[Supplier] = db.get(Supplier, supplier_order.supplier_id)
    if supplier is None:
        supplier_order.status = SupplierOrderStatus.FAILED.value
        db.commit()
        return
    provider = build_provider(supplier)

    attempt = SupplierOrderAttempt(supplier_order_id=supplier_order.id, attempt_no=supplier_order.attempts + 1, action="STATUS")
    db.add(attempt)

    try:
        if supplier_order.external_order_id:
            status = provider.get_order_status(supplier_order.external_order_id)
        else:
            # Submitted but we never got an external id (timeout). Re-submit with
            # the SAME idempotency key — a supplier honoring the key dedupes; this
            # is reconciliation, not a blind duplicate.
            result = provider.create_order(
                external_product_id=_external_id_for(db, supplier_order),
                fields=supplier_order.recipient_payload or {},
                quantity=item.quantity,
                idempotency_key=supplier_order.idempotency_key,
            )
            attempt.outcome = SupplierAttemptOutcome.UNKNOWN.value
            if result.status == "SUCCESS":
                supplier_order.status = SupplierOrderStatus.SUCCESS.value
                supplier_order.completed_at = utcnow()
                supplier_order.external_order_id = result.external_order_id
                item.delivery_state = "COMPLETED"
                db.commit()
                _maybe_finalize_order(db, order)
                return
            if result.status == "PROCESSING":
                supplier_order.status = SupplierOrderStatus.PROCESSING.value
                supplier_order.external_order_id = result.external_order_id
                supplier_order.reconcile_after = utcnow() + RECONCILE_WINDOW * (supplier_order.attempts + 1)
                db.commit()
                _schedule_next_reconcile(supplier_order, order)
                return
            if result.status == "FAILED":
                supplier_order.status = SupplierOrderStatus.FAILED.value
                supplier_order.last_error = result.error
                supplier_order.completed_at = utcnow()
                db.commit()
                _retry_with_next_supplier(db, order, item)
                return
            supplier_order.attempts += 1
            supplier_order.reconcile_after = utcnow() + RECONCILE_WINDOW * (supplier_order.attempts + 1)
            db.commit()
            _schedule_next_reconcile(supplier_order, order)
            return

        # status query path
        supplier_order.attempts += 1
        if status.status == "SUCCESS":
            attempt.outcome = SupplierAttemptOutcome.SUCCESS.value
            supplier_order.status = SupplierOrderStatus.SUCCESS.value
            supplier_order.completed_at = utcnow()
            item.delivery_state = "COMPLETED"
            db.commit()
            _maybe_finalize_order(db, order)
            return
        if status.status == "FAILED":
            attempt.outcome = SupplierAttemptOutcome.FAILURE.value
            attempt.error = (status.error or "")[:500]
            supplier_order.status = SupplierOrderStatus.FAILED.value
            supplier_order.last_error = (status.error or "")[:500]
            supplier_order.completed_at = utcnow()
            db.commit()
            _retry_with_next_supplier(db, order, item)
            return
        if status.status in {"CANCELLED", "REFUNDED"}:
            supplier_order.status = SupplierOrderStatus.CANCELLED.value
            supplier_order.completed_at = utcnow()
            db.commit()
            _retry_with_next_supplier(db, order, item)
            return
        # PROCESSING / UNKNOWN → keep reconciling with bounded lifetime
        attempt.outcome = SupplierAttemptOutcome.UNKNOWN.value
        supplier_order.status = SupplierOrderStatus.PROCESSING.value if status.status == "PROCESSING" else supplier_order.status
        supplier_order.reconcile_after = utcnow() + min(RECONCILE_WINDOW * (supplier_order.attempts + 1), timedelta(minutes=30))
        db.commit()
        _schedule_next_reconcile(supplier_order, order)

    except SupplierProviderError as exc:
        attempt.outcome = SupplierAttemptOutcome.UNKNOWN.value
        attempt.error = str(exc)[:500]
        supplier_order.attempts += 1
        supplier_order.reconcile_after = utcnow() + min(RECONCILE_WINDOW * (supplier_order.attempts + 1), timedelta(minutes=30))
        db.commit()
        _schedule_next_reconcile(supplier_order, order)
    except Exception as exc:
        db.rollback()
        log.exception(f"reconcile failed for supplier order {supplier_order_id}: {exc}")


def _external_id_for(db: DbSession, supplier_order: SupplierOrder) -> str:
    from vyron.db.models import SupplierProduct

    mapping = (
        db.query(SupplierProduct)
        .filter(SupplierProduct.supplier_id == supplier_order.supplier_id)
        .join(OrderItem, OrderItem.variant_id == SupplierProduct.variant_id)
        .filter(OrderItem.id == supplier_order.order_item_id)
        .first()
    )
    return mapping.external_product_id if mapping else ""


def _schedule_next_reconcile(supplier_order: SupplierOrder, order: Order) -> None:
    age = utcnow() - supplier_order.created_at
    if age > timedelta(hours=MAX_RECONCILE_HOURS):
        # Give up automated reconciliation — humans take over; money stays safe.
        from vyron.db.base import get_session_factory  # noqa: F401

        order_service.transition(
            _session_of(supplier_order), order, OrderStatus.MANUAL_REVIEW,
            reason=f"Supplier order {supplier_order.id} unresolved after {MAX_RECONCILE_HOURS}h", actor_type="SYSTEM",
        )
        _notify_admins_delivery_issue(_session_of(supplier_order), order, supplier_order)
        return
    Queue(QueueName.SUPPLIER_STATUS.value).enqueue(
        "reconcile_supplier_order",
        {"supplier_order_id": supplier_order.id},
        dedupe_key=f"reconcile:{supplier_order.id}:{supplier_order.attempts}",
    )


def _session_of(obj) -> DbSession:
    from sqlalchemy.orm import object_session

    session = object_session(obj)
    if session is None:
        raise RuntimeError("object is not attached to a session")
    return session


def _retry_with_next_supplier(db: DbSession, order: Order, item: OrderItem) -> None:
    tried = _tried_supplier_ids(db, item.id)
    candidates = [c for c in candidates_for_variant(db, item.variant_id or "") if c.supplier.id not in tried]
    if not candidates:
        _exhausted_suppliers(db, order, item)
        return
    Queue(QueueName.SUPPLIER_ORDERS.value).enqueue(
        "deliver_order_item", {"order_id": order.id, "order_item_id": item.id}, dedupe_key=f"deliver:{item.id}:retry:{len(tried)}"
    )


def _maybe_finalize_order(db: DbSession, order: Order) -> None:
    db.refresh(order)
    all_done = all(item.delivery_state == "COMPLETED" for item in order.items)
    if not all_done or order.status == OrderStatus.COMPLETED.value:
        return
    order_service.transition(db, order, OrderStatus.COMPLETED, reason="All items delivered", commit=False)
    revenue_service.record_order_completion(db, order)
    user = db.get(User, order.user_id)
    if user:
        notification_service.notify_event(
            db, user, "order_completed", {"number": order.number, "product": order.items[0].product_name if order.items else ""},
            link=f"/dashboard/orders/{order.id}", commit=False,
        )
    audit_service.record_audit(
        db, "order.completed", actor_type="SYSTEM", entity_type="order", entity_id=order.id,
        after={"number": order.number, "total": str(order.total)}, commit=False,
    )
    db.commit()
    log.info("order COMPLETED", number=order.number)


def _no_supplier_available(db: DbSession, order: Order, item: OrderItem) -> None:
    item.delivery_state = "NO_SUPPLIER"
    if order.status not in {OrderStatus.MANUAL_REVIEW.value}:
        order_service.transition(
            db, order, OrderStatus.MANUAL_REVIEW,
            reason="SUPPLIER_NOT_CONFIGURED — no active supplier mapping for this product", commit=False,
        )
    user = db.get(User, order.user_id)
    if user:
        notification_service.notify_event(
            db, user, "order_review", {"number": order.number}, link=f"/dashboard/orders/{order.id}", commit=False
        )
    _notify_admins(db, order, f"No supplier configured for item '{item.variant_name}' (order {order.number}). Payment is captured — fulfil manually or refund.")
    db.commit()
    log.warning("no supplier available — order to MANUAL_REVIEW", number=order.number)


def _exhausted_suppliers(db: DbSession, order: Order, item: OrderItem) -> None:
    item.delivery_state = "FAILED"
    order_service.transition(
        db, order, OrderStatus.MANUAL_REVIEW,
        reason=f"All mapped suppliers failed for item {item.variant_name}", commit=False,
    )
    user = db.get(User, order.user_id)
    if user:
        notification_service.notify_event(db, user, "order_failed", {"number": order.number}, link=f"/dashboard/orders/{order.id}", commit=False)
    _notify_admins(db, order, f"All suppliers failed for '{item.variant_name}' (order {order.number}). Review and refund if needed.")
    db.commit()
    log.error("all suppliers exhausted — MANUAL_REVIEW", number=order.number)


def _recipient_invalid(db: DbSession, order: Order, item: OrderItem, reason: str) -> None:
    item.delivery_state = "VALIDATION_FAILED"
    order_service.transition(
        db, order, OrderStatus.MANUAL_REVIEW, reason=f"Recipient validation failed: {reason[:200]}", commit=False
    )
    user = db.get(User, order.user_id)
    if user:
        notification_service.notify_event(db, user, "order_review", {"number": order.number}, link=f"/dashboard/orders/{order.id}")
    db.commit()


def _notify_admins(db: DbSession, order: Order, message: str) -> None:
    admins = db.query(User).filter(User.role.in_([r.value for r in ADMIN_ROLES])).all()
    for admin in admins:
        db.add(
            Notification(
                user_id=admin.id,
                type="ORDER_FAILED",
                title=f"Delivery attention needed: {order.number}",
                body=message[:500],
                link=f"/admin/orders?q={order.number}",
            )
        )
    db.flush()


def _notify_admins_delivery_issue(db: DbSession, order: Order, supplier_order: SupplierOrder) -> None:
    _notify_admins(
        db, order,
        f"Supplier order {supplier_order.id} for {order.number} stuck in {supplier_order.status} after {supplier_order.attempts} attempts.",
    )


def sync_supplier_catalog(db: DbSession, supplier_id: str, mode: str = "products") -> dict:
    """Admin action: sync products / prices / stock from a supplier."""
    from vyron.db.models import ProductVariant, SupplierProduct
    from vyron.suppliers.router import build_provider

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise SupplierNotConfiguredError("Supplier not found.", code="NOT_FOUND")
    provider = build_provider(supplier)
    if not provider.is_configured():
        supplier.status = "ERROR"
        supplier.last_error = "SUPPLIER_NOT_CONFIGURED"
        db.commit()
        raise SupplierNotConfiguredError(f"Supplier '{supplier.name}' is not configured (no base_url/credentials).")

    try:
        products = provider.get_products()
    except SupplierProviderError as exc:
        supplier.status = "ERROR"
        supplier.last_error = str(exc)[:500]
        db.commit()
        raise
    except SupplierNotConfiguredError:
        supplier.status = "ERROR"
        supplier.last_error = "endpoint 'products' not configured"
        db.commit()
        raise

    updated = created = 0
    for info in products:
        mapping = (
            db.query(SupplierProduct)
            .filter(SupplierProduct.supplier_id == supplier.id, SupplierProduct.external_product_id == info.external_id)
            .first()
        )
        if mapping:
            if mode in {"products", "prices"}:
                mapping.supplier_cost = to_money(info.cost)
                mapping.currency = info.currency
            if mode in {"products", "stock"}:
                mapping.available = info.available
                mapping.stock = info.stock
            mapping.last_synced_at = utcnow()
            updated += 1
        else:
            # Try to attach to a variant by external_product_id match.
            variant = db.query(ProductVariant).filter(ProductVariant.external_product_id == info.external_id).first()
            if variant is not None:
                db.add(
                    SupplierProduct(
                        supplier_id=supplier.id,
                        variant_id=variant.id,
                        external_product_id=info.external_id,
                        supplier_cost=to_money(info.cost),
                        currency=info.currency,
                        available=info.available,
                        stock=info.stock,
                        last_synced_at=utcnow(),
                    )
                )
                created += 1
    supplier.last_sync_at = utcnow()
    supplier.last_error = None
    if supplier.status == "ERROR":
        supplier.status = "ACTIVE"
    db.commit()
    return {"updated": updated, "created": created, "fetched": len(products)}


def test_supplier_connection(db: DbSession, supplier_id: str) -> dict:
    from vyron.suppliers.router import build_provider

    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise SupplierNotConfiguredError("Supplier not found.", code="NOT_FOUND")
    provider = build_provider(supplier)
    if not provider.is_configured():
        supplier.last_error = "SUPPLIER_NOT_CONFIGURED"
        db.commit()
        raise SupplierNotConfiguredError(f"Supplier '{supplier.name}' is not configured.")
    try:
        result = provider.test_connection()
        balance = provider.get_balance()
        supplier.balance = balance.balance
        supplier.balance_currency = balance.currency
        supplier.balance_checked_at = utcnow()
        supplier.last_error = None
        if supplier.status == "ERROR":
            supplier.status = "ACTIVE"
        db.commit()
        return {"ok": bool(result.get("ok")), "balance": str(balance.balance) if balance.balance is not None else None, "currency": balance.currency}
    except (SupplierProviderError, SupplierNotConfiguredError) as exc:
        supplier.last_error = str(exc)[:500]
        supplier.status = "ERROR"
        db.commit()
        raise
