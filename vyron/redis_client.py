"""Shared Redis client (queues, rate limiting, locks, caches)."""

from __future__ import annotations

import redis

from vyron.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            health_check_interval=30,
        )
    return _client


def redis_ping() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False


def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        finally:
            _client = None
