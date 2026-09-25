"""Webhook endpoints: payment provider + Payerpin supplier events.

Both endpoints are idempotent (delivery IDs stored), signature-verified
(HMAC-SHA256, constant-time compare), and use the ORIGINAL raw body.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.logging_config import get_logger
from app.models import (
    Fulfillment,
    FulfillmentStatus,
    Order,
    OrderStatus,
    Supplier,
    SupplierTransaction,
    WebhookEvent,
)
from app.providers.suppliers.payerpin import get_payerpin, map_supplier_status
from app.security import verify_hmac_signature
from app.services.fulfillment import FulfillmentService
from app.services.payments import PaymentError, process_payment_webhook

log = get_logger("vyron.webhooks")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/payments")
async def payment_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_payment_delivery_id: Optional[str] = Header(default=None),
):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        result = process_payment_webhook(
            db,
            raw_body=raw,
            headers=headers,
            payload=payload,
        )
        db.commit()
        return result
    except PaymentError as exc:
        db.rollback()
        status = 400 if exc.key in ("invalid_signature", "amount_mismatch", "currency_mismatch") else 404
        if exc.key == "payment_not_configured":
            status = 503
        raise HTTPException(status_code=status, detail=exc.key)


@router.post("/payerpin")
async def payerpin_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_payerpin_signature: Optional[str] = Header(default=None),
    x_payerpin_timestamp: Optional[str] = Header(default=None),
    x_payerpin_delivery_id: Optional[str] = Header(default=None),
):
    """Payerpin fulfillment events:
    order.completed / order.failed / order.refunded / payment.succeeded

    Signature: HMAC-SHA256 over `timestamp + '.' + rawBody`.
    """
    from app.config import get_settings

    raw = await request.body()
    settings = get_settings()
    secret = settings.payment_webhook_secret  # shared webhook secret scheme
    # Prefer a dedicated supplier webhook secret if configured via settings table
    delivery_id = x_payerpin_delivery_id or f"auto:{hash(raw)}"

    existing = db.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == "payerpin",
            WebhookEvent.delivery_id == str(delivery_id),
        )
    ).scalar_one_or_none()
    if existing is not None and existing.processed:
        return {"status": "duplicate"}

    signature_valid = verify_hmac_signature(
        secret, raw, x_payerpin_timestamp or "", x_payerpin_signature or ""
    )
    event = existing or WebhookEvent(
        provider="payerpin",
        delivery_id=str(delivery_id),
        signature_valid=signature_valid,
        payload=None,
    )
    if existing is None:
        db.add(event)
        db.flush()

    if not signature_valid:
        log.warning("payerpin webhook invalid signature delivery=%s", delivery_id)
        raise HTTPException(status_code=400, detail="invalid_signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    event_type = payload.get("event") or payload.get("type")
    event.event_type = event_type
    event.payload = payload

    data = payload.get("data") or payload.get("order") or payload
    supplier_order_id = str(
        data.get("id") or data.get("orderId") or data.get("order_id") or ""
    )
    raw_status = data.get("status")
    status = map_supplier_status(raw_status)

    tx = None
    if supplier_order_id:
        tx = db.execute(
            select(SupplierTransaction).where(
                SupplierTransaction.supplier_order_id == supplier_order_id
            )
        ).scalars().first()
    if tx is None:
        reference = data.get("reference") or data.get("clientReference")
        if reference:
            order = db.execute(
                select(Order).where(Order.order_number == str(reference))
            ).scalar_one_or_none()
            if order is not None and order.items:
                tx = db.execute(
                    select(SupplierTransaction).where(SupplierTransaction.order_id == order.id)
                ).scalars().first()

    if tx is None:
        event.processed = True
        event.processed_at = datetime.utcnow()
        log.warning("payerpin webhook unknown order delivery=%s", delivery_id)
        return {"status": "ignored_unknown_order"}

    service = FulfillmentService()
    if event_type in ("order.refunded",):
        service.record_supplier_result(
            db, tx.id, supplier_order_id=tx.supplier_order_id,
            status="FAILED", raw={"event": event_type, "data": data},
            error_code="REFUNDED", error_message="Supplier reported refund",
        )
        tx.order.status = OrderStatus.REFUNDED
    elif status == "COMPLETED" or event_type == "order.completed":
        service.record_supplier_result(
            db, tx.id, supplier_order_id=tx.supplier_order_id or supplier_order_id,
            status="COMPLETED", raw={"event": event_type, "data": data},
        )
    elif status == "FAILED" or event_type == "order.failed":
        service.record_supplier_result(
            db, tx.id, supplier_order_id=tx.supplier_order_id or supplier_order_id,
            status="FAILED", raw={"event": event_type, "data": data},
            error_code="SUPPLIER_FAILED", error_message="Supplier reported failure",
        )
    else:
        # Unknown statuses never become COMPLETED.
        service.record_supplier_result(
            db, tx.id, supplier_order_id=tx.supplier_order_id or supplier_order_id,
            status="PROCESSING", raw={"event": event_type, "data": data},
        )

    event.processed = True
    event.processed_at = datetime.utcnow()
    db.commit()
    return {"status": "processed"}
