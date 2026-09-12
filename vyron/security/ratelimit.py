"""Redis-backed rate limiting (fixed-window counters).

Applied to login, registration, password reset, email verification and
webhook ingestion. Identifiers: IP address and/or authenticated user id.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from vyron.errors import RateLimitedError
from vyron.logging import get_logger
from vyron.redis_client import get_redis
from vyron.security.sessions import client_ip

log = get_logger("vyron.ratelimit")

WINDOW_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}


@dataclass
class RateLimitSpec:
    limit: int
    window: int  # seconds

    @classmethod
    def parse(cls, spec: str) -> RateLimitSpec:
        """Parse '10/minute' style specs."""
        raw_count, _, raw_window = spec.partition("/")
        window = WINDOW_SECONDS.get(raw_window.strip().lower(), 60)
        return cls(limit=int(raw_count.strip()), window=window)


def check_rate_limit(scope: str, identifier: str, spec: RateLimitSpec) -> tuple[bool, int]:
    """Returns (allowed, retry_after_seconds). Fail-open if Redis is down is NOT
    acceptable for auth endpoints, but Redis is a hard dependency checked at boot;
    if a transient error occurs we allow and log (availability over strictness)."""
    redis = get_redis()
    window_start = int(time.time()) // spec.window
    key = f"vyron:rl:{scope}:{identifier}:{window_start}"
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, spec.window + 1)
        count, _ = pipe.execute()
    except Exception as exc:  # pragma: no cover - transient redis failure
        log.warning(f"rate limiter error (allowing): {exc}", scope=scope)
        return True, 0
    count = int(count)
    if count > spec.limit:
        retry_after = spec.window - (int(time.time()) % spec.window)
        return False, retry_after
    return True, 0


def enforce_rate_limit(request: Request, scope: str, spec_str: str, user_id: Optional[str] = None) -> None:
    spec = RateLimitSpec.parse(spec_str)
    ident = user_id or client_ip(request) or "anonymous"
    allowed, retry_after = check_rate_limit(scope, ident, spec)
    if not allowed:
        log.warning("rate limit exceeded", scope=scope, ident=ident)
        raise RateLimitedError(f"Too many attempts. Please try again in {retry_after} seconds.")
