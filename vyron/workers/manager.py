"""WorkerManager — starts/stops all queue consumers + the periodic scheduler
in daemon threads. Used by main.py so `python main.py` runs the whole system."""

from __future__ import annotations

import threading
from typing import List

from vyron.logging import get_logger
from vyron.queue.engine import Queue, QueueWorker
from vyron.workers.handlers import HANDLERS_BY_QUEUE
from vyron.workers.scheduler import Scheduler

log = get_logger("vyron.workers.manager")


class WorkerManager:
    def __init__(self) -> None:
        self.workers: List[QueueWorker] = []
        self.threads: List[threading.Thread] = []
        self.scheduler: Scheduler | None = None

    def start(self) -> None:
        for queue_name, handlers in HANDLERS_BY_QUEUE.items():
            queue = Queue(queue_name)
            queue.ensure_group()
            worker = QueueWorker(queue, consumer_name=f"{queue_name}-1", handlers=handlers)
            thread = threading.Thread(target=worker.run, name=f"worker-{queue_name}", daemon=True)
            thread.start()
            self.workers.append(worker)
            self.threads.append(thread)
            log.info("queue worker started", queue=queue_name, tasks=sorted(handlers))

        self.scheduler = Scheduler()
        self.scheduler.start()
        log.info("all workers running", count=len(self.workers))

    def stop(self) -> None:
        for worker in self.workers:
            worker.stop()
        if self.scheduler:
            self.scheduler.stop()
        for thread in self.threads:
            thread.join(timeout=5)
        log.info("workers stopped")


def start_workers() -> WorkerManager:
    manager = WorkerManager()
    manager.start()
    return manager
