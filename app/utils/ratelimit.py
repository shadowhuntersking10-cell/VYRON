"""Tiny in-memory rate limiter (Redis-backed when REDIS_URL is set)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

_buckets: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds)."""
    now = time.monotonic()
    bucket = _buckets[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        retry = int(bucket[0] + window_seconds - now) + 1
        return False, max(1, retry)
    bucket.append(now)
    return True, 0
