"""Automatic order processing: PAID -> supplier -> COMPLETED.

- Creates supplier orders with idempotency keys (no duplicates)
- Polls supplier status, retries with limits
- On repeated failure -> MANUAL_REVIEW
- On missing supplier credentials -> SUPPLIER_NOT_CONFIGURED -> MANUAL_REVIEW
- Writes revenue ledger entries on completion
- Notifies the user at every step
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, OrderItem, OrderStatus, Product, SupplierOrder
from app.services.notification_service import notify_order_event
from app.services.revenue_service import record_order_revenue
from app.suppliers.base import SupplierError, SupplierNotConfigured
from app.suppliers.manager import get_supplier_manager
from app.utils.helpers import utcnow

log = logging.getLogger("vyron.orders")

MAX_SUPPLIER_ATTEMPTS = 5


def _touch(order: Order, event: str, **extra) -> None:
    order.timeline = (order.timeline or []) + [{"event": event, "at": utcnow().isoformat(), **extra}]


class OrderProcessor:
    async def on_payment_confirmed(self, db: AsyncSession, order: Order) -> Order:
        """Entry point after payment verification. Routes by item kind."""
        await db.refresh(order, attribute_names=["items"])
        kinds = {i.kind for i in order.items}
        if kinds == {"marketplace"}:
            return await self._fulfil_marketplace(db, order)
        if kinds == {"donation"}:
            return await self._fulfil_donation(db, order)
        return await self._fulfil_topup(db, order)

    # ---- top-up flow ----
    async def _fulfil_topup(self, db: AsyncSession, order: Order) -> Order:
        order.status = OrderStatus.PROCESSING
        _touch(order, "processing")
        await db.flush()
        await notify_order_event(db, user_id=order.user_id, title="Order processing",
                                 body=f"Order {order.public_id} is being processed.",
                                 link=f"/app/orders/{order.public_id}")
        await db.commit()

        suppliers = get_supplier_manager()
        for item in order.items:
            if item.kind != "product":
                continue
            product = await db.get(Product, item.product_id) if item.product_id else None
            if not product:
                order.status = OrderStatus.MANUAL_REVIEW
                _touch(order, "manual_review", reason="product_missing")
                continue
            provider, supplier_row = await suppliers.provider_for_product(db, product)
            if not provider.configured:
                order.status = OrderStatus.SUPPLIER_NOT_CONFIGURED
                _touch(order, "supplier_not_configured", provider=provider.code)
                await db.flush()
                await notify_order_event(db, user_id=order.user_id, title="Order needs review",
                                         body=f"Order {order.public_id}: supplier not configured. Support will handle it.",
                                         link=f"/app/orders/{order.public_id}")
                continue
            await self._create_supplier_order(db, order, item, provider, supplier_row.id if supplier_row else None)
        await db.commit()
        return order

    async def _create_supplier_order(self, db, order: Order, item: OrderItem, provider, supplier_id: int | None) -> None:
        key = f"sup-{order.public_id}-{item.id}"
        existing = (await db.execute(select(SupplierOrder).where(SupplierOrder.idempotency_key == key))).scalars().first()
        if existing:
            return
        product = await db.get(Product, item.product_id) if item.product_id else None
        external_product_id = ""
        if item.variant_id:
            from app.models import ProductVariant
            var = await db.get(ProductVariant, item.variant_id)
            external_product_id = (var.supplier_product_id if var else "") or ""
        if not external_product_id and product:
            external_product_id = product.supplier_product_id or ""

        sup_order = SupplierOrder(
            order_id=order.id, supplier_id=supplier_id, idempotency_key=key,
            status="QUEUED",
            payload={"product": external_product_id, "fields": order.customer_fields, "quantity": item.quantity},
        )
        db.add(sup_order)
        await db.flush()

        if provider.code == "manual":
            order.status = OrderStatus.MANUAL_REVIEW
            _touch(order, "manual_review", reason="manual_supplier")
            sup_order.status = "QUEUED"
            await db.flush()
            await notify_order_event(db, user_id=order.user_id, title="Order received",
                                     body=f"Order {order.public_id} is queued for manual delivery.",
                                     link=f"/app/orders/{order.public_id}")
            return

        try:
            result = await provider.create_order(
                external_product_id=external_product_id,
                customer_fields=order.customer_fields or {},
                quantity=item.quantity,
                idempotency_key=key,
            )
        except (SupplierError, SupplierNotConfigured) as exc:
            sup_order.status = "QUEUED"
            sup_order.attempts += 1
            sup_order.last_error = str(exc)[:500]
            order.status = OrderStatus.MANUAL_REVIEW
            _touch(order, "supplier_error", error=str(exc)[:200])
            await db.flush()
            return

        sup_order.external_order_id = result.external_order_id
        sup_order.status = result.status
        sup_order.response = result.raw
        order.status = OrderStatus.SUPPLIER_PROCESSING
        _touch(order, "supplier_processing", supplier_order=result.external_order_id)
        await db.flush()
        await notify_order_event(db, user_id=order.user_id, title="Top-up in progress",
                                 body=f"Order {order.public_id} was sent to the game supplier.",
                                 link=f"/app/orders/{order.public_id}")

    async def poll_supplier_orders(self, db: AsyncSession, *, limit: int = 50) -> int:
        """Background job: poll QUEUED/PROCESSING supplier orders."""
        stmt = (
            select(SupplierOrder)
            .where(SupplierOrder.status.in_(["QUEUED", "PROCESSING"]))
            .where(SupplierOrder.external_order_id.is_not(None))
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()
        suppliers = get_supplier_manager()
        provider = suppliers.get("generic")
        if not provider.configured:
            return 0
        processed = 0
        for sup in rows:
            try:
                res = await provider.get_order_status(sup.external_order_id or "")
            except SupplierError as exc:
                sup.attempts += 1
                sup.last_error = str(exc)[:500]
                if sup.attempts >= MAX_SUPPLIER_ATTEMPTS:
                    sup.status = "FAILED"
                    order = await db.get(Order, sup.order_id)
                    if order:
                        order.status = OrderStatus.MANUAL_REVIEW
                        _touch(order, "manual_review", reason="supplier_poll_failed")
                await db.flush()
                continue
            sup.status = res.status
            sup.response = res.raw
            order = await db.get(Order, sup.order_id)
            if res.status == "COMPLETED" and order:
                await self.complete_order(db, order)
            elif res.status in ("FAILED", "CANCELLED") and order:
                order.status = OrderStatus.MANUAL_REVIEW
                _touch(order, "manual_review", reason=f"supplier_{res.status.lower()}")
                await notify_order_event(db, user_id=order.user_id, title="Order needs review",
                                         body=f"Order {order.public_id}: supplier reported {res.status}.",
                                         link=f"/app/orders/{order.public_id}")
            await db.flush()
            processed += 1
        await db.commit()
        return processed

    async def complete_order(self, db: AsyncSession, order: Order) -> Order:
        if order.status == OrderStatus.COMPLETED:
            return order
        order.status = OrderStatus.COMPLETED
        order.completed_at = utcnow()
        _touch(order, "completed")
        await record_order_revenue(db, order)
        await db.flush()
        await notify_order_event(db, user_id=order.user_id, title="Order completed ✅",
                                 body=f"Order {order.public_id} is complete. Thank you!",
                                 link=f"/app/orders/{order.public_id}")
        await db.commit()
        return order

    async def fail_order(self, db: AsyncSession, order: Order, reason: str) -> Order:
        order.status = OrderStatus.FAILED
        _touch(order, "failed", reason=reason)
        await db.flush()
        await notify_order_event(db, user_id=order.user_id, title="Order failed",
                                 body=f"Order {order.public_id} failed: {reason}",
                                 link=f"/app/orders/{order.public_id}")
        await db.commit()
        return order

    # ---- marketplace flow: credit seller (minus commission), notify parties ----
    async def _fulfil_marketplace(self, db: AsyncSession, order: Order) -> Order:
        from app.services.marketplace_service import settle_marketplace_order

        await settle_marketplace_order(db, order)
        await self.complete_order(db, order)
        return order

    # ---- donation flow ----
    async def _fulfil_donation(self, db: AsyncSession, order: Order) -> Order:
        from app.services.donation_service import settle_donation_order

        await settle_donation_order(db, order)
        await self.complete_order(db, order)
        return order

    async def process_paid_orders(self, db: AsyncSession, *, limit: int = 20) -> int:
        """Safety-net worker: picks up PAID orders that missed the webhook path."""
        stmt = select(Order).where(Order.status == OrderStatus.PAID).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        for order in rows:
            try:
                await self.on_payment_confirmed(db, order)
            except Exception as exc:  # noqa: BLE001 - worker must continue
                log.exception("failed processing order %s: %s", order.public_id, exc)
        return len(rows)


_processor: OrderProcessor | None = None


def get_order_processor() -> OrderProcessor:
    global _processor
    if _processor is None:
        _processor = OrderProcessor()
    return _processor
