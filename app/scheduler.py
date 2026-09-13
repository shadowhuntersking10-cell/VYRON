"""Background workers + scheduled tasks (started from main.py)."""
from __future__ import annotations

import asyncio
import logging

from app.database import get_session_factory
from app.orders.processor import get_order_processor

log = logging.getLogger("vyron.worker")


async def _loop(name: str, interval: int, fn) -> None:
    log.info("worker started: %s (every %ss)", name, interval)
    while True:
        try:
            await asyncio.sleep(interval)
            factory = get_session_factory()
            async with factory() as db:
                await fn(db)
        except asyncio.CancelledError:
            log.info("worker stopped: %s", name)
            raise
        except Exception:  # noqa: BLE001 - workers must never die
            log.exception("worker error: %s", name)


async def _process_paid(db) -> None:
    n = await get_order_processor().process_paid_orders(db)
    if n:
        log.info("processed %d paid orders", n)


async def _poll_suppliers(db) -> None:
    n = await get_order_processor().poll_supplier_orders(db)
    if n:
        log.info("polled %d supplier orders", n)


def start_workers() -> list[asyncio.Task]:
    return [
        asyncio.create_task(_loop("process_paid_orders", 30, _process_paid)),
        asyncio.create_task(_loop("poll_suppliers", 60, _poll_suppliers)),
    ]


async def stop_workers(tasks: list[asyncio.Task]) -> None:
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
