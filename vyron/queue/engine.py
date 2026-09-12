"""Redis Streams queue engine — VYRON's job infrastructure (BullMQ-equivalent).

Features:
- named queues: supplier-orders, supplier-status, payments, notifications,
  emails, telegram, fraud, refunds, payouts
- consumer groups with XREADGROUP / XACK
- retries with exponential backoff, per-message attempt counter
- dead-letter stream after max attempts (inspectable, replayable)
- dedupe keys (SETNX) for idempotent enqueue
- scheduled/periodic jobs via interval locks
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import redis

from vyron.logging import get_logger
from vyron.redis_client import get_redis

log = get_logger("vyron.queue")

QUEUE_PREFIX = "vyron:queue:"
DLQ_PREFIX = "vyron:dlq:"
DEDUPE_PREFIX = "vyron:dedupe:"
LOCK_PREFIX = "vyron:lock:"

DEFAULT_MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 10.0
CLAIM_IDLE_MS = 30 * 1000  # reclaim pending (delayed/stuck) messages after 30s idle

Handler = Callable[[Dict[str, Any], "JobContext"], None]


@dataclass
class JobContext:
    queue: str
    message_id: str
    attempts: int = 1
    payload: Dict[str, Any] = field(default_factory=dict)


class RetryJob(Exception):
    """Handler raises this to request a retry with backoff."""

    def __init__(self, reason: str = "", delay_seconds: Optional[float] = None) -> None:
        self.reason = reason
        self.delay_seconds = delay_seconds
        super().__init__(reason)


class DropJob(Exception):
    """Handler raises this to drop the job without retry (logged)."""


class Queue:
    def __init__(self, name: str, redis_client: Optional[redis.Redis] = None) -> None:
        self.name = name
        self.stream = f"{QUEUE_PREFIX}{name}"
        self.group = f"{name}-workers"
        self.dlq = f"{DLQ_PREFIX}{name}"
        self._redis = redis_client

    @property
    def r(self) -> redis.Redis:
        return self._redis or get_redis()

    def ensure_group(self) -> None:
        try:
            self.r.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def enqueue(
        self,
        task: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        dedupe_key: Optional[str] = None,
        dedupe_ttl: int = 86400,
    ) -> Optional[str]:
        """Add a job. If dedupe_key was already used within its TTL, skip (idempotent enqueue)."""
        if dedupe_key:
            key = f"{DEDUPE_PREFIX}{self.name}:{dedupe_key}"
            if not self.r.set(key, "1", nx=True, ex=dedupe_ttl):
                log.info("duplicate enqueue skipped", queue=self.name, task=task, dedupe=dedupe_key)
                return None
        message = {
            "id": str(uuid.uuid4()),
            "task": task,
            "payload": json.dumps(payload or {}, default=str),
            "attempts": "0",
            "enqueued_at": str(time.time()),
        }
        message_id: str = self.r.xadd(self.stream, message, maxlen=100000, approximate=True)
        log.info("job enqueued", queue=self.name, task=task, message_id=message_id)
        return message_id

    def requeue_later(self, task: str, payload: Dict[str, Any], attempts: int, max_attempts: int) -> None:
        """Schedule a retry by re-enqueueing with attempt metadata (delay handled by worker poll)."""
        message = {
            "id": str(uuid.uuid4()),
            "task": task,
            "payload": json.dumps(payload, default=str),
            "attempts": str(attempts),
            "max_attempts": str(max_attempts),
            "not_before": str(time.time() + backoff_delay(attempts)),
            "enqueued_at": str(time.time()),
        }
        self.r.xadd(self.stream, message, maxlen=100000, approximate=True)

    def to_dlq(self, message: Dict[str, str], error: str) -> None:
        entry = dict(message)
        entry["failed_at"] = str(time.time())
        entry["error"] = error[:2000]
        self.r.xadd(self.dlq, entry, maxlen=10000, approximate=True)
        log.error("job moved to DLQ", queue=self.name, task=message.get("task"), error=error[:300])

    def depth(self) -> int:
        try:
            return int(self.r.xlen(self.stream))
        except redis.RedisError:
            return -1

    def dlq_depth(self) -> int:
        try:
            return int(self.r.xlen(self.dlq))
        except redis.RedisError:
            return -1


def backoff_delay(attempts: int) -> float:
    """Exponential backoff: 10s, 20s, 40s, 80s ... capped at 30 min."""
    return min(BASE_BACKOFF_SECONDS * (2 ** max(0, attempts - 1)), 1800.0)


class QueueWorker:
    """Consumes one queue: dispatches tasks to handlers, retries, DLQs."""

    def __init__(self, queue: Queue, consumer_name: str, handlers: Dict[str, Handler], max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> None:
        self.queue = queue
        self.consumer_name = consumer_name
        self.handlers = handlers
        self.max_attempts = max_attempts
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        """Blocking consumer loop — run one QueueWorker per thread."""
        self.queue.ensure_group()
        log.info("queue worker started", queue=self.queue.name, consumer=self.consumer_name, tasks=sorted(self.handlers))
        while not self._stop:
            try:
                self.poll_once()
            except redis.RedisError as exc:
                log.warning("worker redis error, backing off", queue=self.queue.name, error=str(exc))
                time.sleep(2.0)
            except Exception:
                log.exception("worker loop error")
                time.sleep(1.0)
        log.info("queue worker stopped", queue=self.queue.name)

    def claim_stale(self) -> List[Any]:
        """Reclaim pending messages from dead consumers (at-least-once delivery)."""
        try:
            return self.queue.r.xautoclaim(
                self.queue.stream, self.queue.group, self.consumer_name, min_idle_time=CLAIM_IDLE_MS, start_id="0-0", count=10
            )
        except redis.ResponseError:
            return []

    def process_batch(self, batch: List[Any], from_claim: bool = False) -> int:
        processed = 0
        for entry in batch:
            if self._stop:
                break
            if from_claim:
                message_id, fields = entry
                if not fields:
                    self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
                    continue
            else:
                message_id, fields = entry
            try:
                processed += self.handle_one(message_id, fields)
            except Exception:
                log.exception("unexpected worker loop error")
        return processed

    def handle_one(self, message_id: str, fields: Dict[str, str]) -> int:
        task = fields.get("task", "")
        raw_payload = fields.get("payload", "{}")
        attempts = int(fields.get("attempts", "0")) + 1
        max_attempts = int(fields.get("max_attempts", str(self.max_attempts)))
        not_before = float(fields.get("not_before", "0"))

        if not_before and time.time() < not_before:
            return 0  # not due yet; leave pending, claim loop will pick it up later

        handler = self.handlers.get(task)
        if handler is None:
            self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
            self.queue.to_dlq(fields, f"no handler registered for task '{task}'")
            return 0

        try:
            payload = json.loads(raw_payload)
        except ValueError:
            payload = {}

        context = JobContext(queue=self.queue.name, message_id=message_id, attempts=attempts, payload=payload)
        try:
            handler(payload, context)
            self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
            return 1
        except RetryJob as retry:
            self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
            if attempts >= max_attempts:
                self.queue.to_dlq(fields, f"max attempts exceeded: {retry.reason}")
            else:
                delay = retry.delay_seconds if retry.delay_seconds is not None else backoff_delay(attempts)
                due = {**fields, "attempts": str(attempts), "max_attempts": str(max_attempts), "not_before": str(time.time() + delay)}
                self.queue.r.xadd(self.queue.stream, due, maxlen=100000, approximate=True)
                log.warning("job retry scheduled", queue=self.queue.name, task=task, attempts=attempts, delay=delay, reason=retry.reason)
            return 0
        except DropJob as drop:
            self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
            log.warning("job dropped by handler", queue=self.queue.name, task=task, reason=str(drop))
            return 0
        except Exception as exc:
            self.queue.r.xack(self.queue.stream, self.queue.group, message_id)
            if attempts >= max_attempts:
                self.queue.to_dlq(fields, f"{type(exc).__name__}: {exc}")
            else:
                due = {**fields, "attempts": str(attempts), "max_attempts": str(max_attempts), "not_before": str(time.time() + backoff_delay(attempts))}
                self.queue.r.xadd(self.queue.stream, due, maxlen=100000, approximate=True)
                log.error("job failed, retry scheduled", queue=self.queue.name, task=task, attempts=attempts, error=str(exc)[:300])
            return 0

    def poll_once(self, block_ms: int = 2000, count: int = 16) -> int:
        self.queue.ensure_group()
        processed = 0
        claim = self.claim_stale()
        if claim:
            # xautoclaim returns (next_start, claimed, deleted_ids)
            claimed = claim[1] if len(claim) >= 2 else []
            processed += self.process_batch(claimed, from_claim=True)
        response = self.queue.r.xreadgroup(
            self.queue.group, self.consumer_name, {self.queue.stream: ">"}, count=count, block=block_ms
        )
        if response:
            for _stream, batch in response:
                processed += self.process_batch(batch)
        return processed


def acquire_interval_lock(name: str, interval_seconds: int) -> bool:
    """SETNX-based lock so periodic tasks run once per interval across processes."""
    r = get_redis()
    return bool(r.set(f"{LOCK_PREFIX}{name}", "1", nx=True, ex=interval_seconds))
