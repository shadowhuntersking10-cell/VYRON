"""Background workers + scheduled jobs (asyncio tasks, no external broker needed)."""
from __future__ import annotations

import asyncio
import datetime as dt

from app.database import SessionLocal
from app.utils.logging import get_logger

log = get_logger("vyron.worker")


async def _cleanup_sessions(stop: asyncio.Event):
    from app import models
    while not stop.is_set():
        try:
            db = SessionLocal()
            try:
                n = db.query(models.UserSession).filter(
                    models.UserSession.expires_at < dt.datetime.utcnow()).delete()
                db.commit()
                if n:
                    log.info("cleaned %s expired sessions", n)
            finally:
                db.close()
        except Exception as exc:
            log.error("session cleanup failed: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=3600)
        except asyncio.TimeoutError:
            pass


async def _poll_supplier_orders(stop: asyncio.Event):
    """Poll supplier status for SUPPLIER_PROCESSING orders; complete only on real confirmation."""
    from app import models
    from app.suppliers import get_adapter
    from app.services import orders as order_svc

    while not stop.is_set():
        try:
            db = SessionLocal()
            try:
                orders = db.query(models.Order).filter_by(status="SUPPLIER_PROCESSING").limit(20).all()
                for o in orders:
                    sup = db.query(models.SupplierOrder).filter_by(order_id=o.id).order_by(
                        models.SupplierOrder.id.desc()).first()
                    if not sup or not sup.external_order_id:
                        continue
                    supplier = db.get(models.Supplier, sup.supplier_id) if sup.supplier_id else None
                    adapter = get_adapter(supplier)
                    if not adapter or not adapter.is_configured():
                        continue
                    try:
                        res = adapter.get_order_status(sup.external_order_id)
                        status = str(res.get("status", "")).lower()
                        sup.response = str(res)[:4000]
                        if status in ("completed", "delivered", "success", "done"):
                            order_svc.set_status(o, "COMPLETED", "supplier confirmed")
                            from app.services import notify
                            if o.user_id:
                                notify.create(db, o.user_id, "order_completed", "order_completed",
                                              o.public_id, f"/orders/{o.public_id}")
                        elif status in ("failed", "cancelled", "error"):
                            order_svc.set_status(o, "FAILED", f"supplier: {status}")
                        db.commit()
                    except Exception as exc:
                        sup.attempts = (sup.attempts or 0) + 1
                        sup.last_error = str(exc)[:500]
                        db.commit()
            finally:
                db.close()
        except Exception as exc:
            log.error("supplier poll failed: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


async def run_workers(stop_event: asyncio.Event) -> None:
    log.info("background workers started")
    await asyncio.gather(_cleanup_sessions(stop_event), _poll_supplier_orders(stop_event))
    log.info("background workers stopped")
