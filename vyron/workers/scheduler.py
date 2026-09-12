"""Periodic background services (single-flight via Redis interval locks).

Jobs:
- every 60s:  payment reconciliation — re-check PAYMENT_PENDING payments against providers
- every 60s:  supplier order sweep — re-enqueue reconciliation for stuck supplier orders
- every 5m:   release seller balances whose holding period elapsed (pending -> available)
- every 5m:   expire finished listing promotions & seller subscriptions
"""

from __future__ import annotations

import threading
from typing import Callable, List, Tuple

from sqlalchemy import select

from vyron.db.base import get_session_factory, utcnow
from vyron.enums import QueueName, SupplierOrderStatus
from vyron.logging import get_logger
from vyron.queue.engine import Queue, acquire_interval_lock

log = get_logger("vyron.workers.scheduler")

POLL_SECONDS = 10


def _session():
    return get_session_factory()()


def job_reconcile_payments() -> None:
    from vyron.services import payment_service

    db = _session()
    try:
        n = payment_service.reconcile_stale_payments(db, limit=50)
        db.commit()
        if n:
            log.info("reconciled stale payments", count=n)
    except Exception as exc:
        db.rollback()
        log.warning("payment reconciliation failed", error=str(exc))
    finally:
        db.close()


def job_sweep_supplier_orders() -> None:
    from vyron.db.models import SupplierOrder

    db = _session()
    try:
        now = utcnow()
        rows = db.scalars(
            select(SupplierOrder)
            .where(
                SupplierOrder.status.in_(
                    [SupplierOrderStatus.SUBMITTED.value, SupplierOrderStatus.PROCESSING.value, SupplierOrderStatus.UNKNOWN.value]
                ),
                SupplierOrder.reconcile_after <= now,
            )
            .limit(100)
        ).all()
        queue = Queue(QueueName.SUPPLIER_STATUS.value)
        for so in rows:
            queue.enqueue(
                "reconcile_supplier_order",
                {"supplier_order_id": so.id},
                dedupe_key=f"reconcile:{so.id}:sweep:{int(now.timestamp() // 300)}",
            )
        db.commit()
        if rows:
            log.info("supplier sweep re-queued reconciliations", count=len(rows))
    except Exception as exc:
        db.rollback()
        log.warning("supplier sweep failed", error=str(exc))
    finally:
        db.close()


def job_release_balances() -> None:
    from vyron.services import seller_service

    db = _session()
    try:
        n = seller_service.release_pending_balances(db, limit=500)
        db.commit()
        if n:
            log.info("released pending seller balances", count=n)
    except Exception as exc:
        db.rollback()
        log.warning("balance release failed", error=str(exc))
    finally:
        db.close()


def job_expire_seller_extras() -> None:
    from vyron.services import seller_service

    db = _session()
    try:
        result = seller_service.expire_promotions_and_subscriptions(db)
        db.commit()
        if any(result.values()):
            log.info("expired promotions/subscriptions", **result)
    except Exception as exc:
        db.rollback()
        log.warning("expire promotions/subscriptions failed", error=str(exc))
    finally:
        db.close()


JOBS: List[Tuple[str, int, Callable[[], None]]] = [
    ("reconcile-payments", 60, job_reconcile_payments),
    ("sweep-supplier-orders", 60, job_sweep_supplier_orders),
    ("release-balances", 300, job_release_balances),
    ("expire-seller-extras", 300, job_expire_seller_extras),
]


class Scheduler(threading.Thread):
    """Daemon thread that runs periodic jobs, guarded by Redis interval locks
    so multiple processes never double-execute the same tick."""

    def __init__(self) -> None:
        super().__init__(name="vyron-scheduler", daemon=True)
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        log.info("scheduler started", jobs=[j[0] for j in JOBS])
        while not self._stop.is_set():
            for name, interval, fn in JOBS:
                if self._stop.is_set():
                    break
                try:
                    if acquire_interval_lock(f"sched:{name}", interval):
                        fn()
                except Exception as exc:
                    log.warning("scheduler tick failed", job=name, error=str(exc))
            self._stop.wait(POLL_SECONDS)
        log.info("scheduler stopped")
