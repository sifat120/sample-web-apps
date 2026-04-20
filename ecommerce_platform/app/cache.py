"""
cache.py — Valkey client connection

Valkey is used in this app for:
  - Product page caching (avoids repeated PostgreSQL queries)
  - Shopping cart storage (fast, ephemeral, TTL-based)
  - Rate limiting (per-IP request counters)
  - Session tokens (logged-in user state)

What is Valkey?
  Valkey is a community-maintained, BSD-licensed fork of Redis. It was
  created in 2024 after Redis Ltd. changed Redis to a non-open-source
  license (SSPL). Valkey is maintained by the Linux Foundation and is
  100% protocol-compatible with Redis — existing clients, commands, and
  data structures all work identically.

  We use the redis-py library (imported as "redis.asyncio") to connect
  to Valkey. No code changes are needed compared to using Redis itself —
  the wire protocol is identical.

Local:      Valkey running in Docker (see docker-compose.yml)
Production: AWS ElastiCache for Valkey, Upstash, or Aiven for Valkey
            (see .env.example for connection string examples)

This module uses the "singleton" pattern: the Valkey connection is
created once the first time get_redis() is called, then reused for
every subsequent call. Creating a new connection per request is wasteful.
"""

import redis.asyncio as valkey_client  # redis-py is protocol-compatible with Valkey

from app.config import settings


# Module-level variable holding the single shared Valkey connection.
# Starts as None and is set the first time get_redis() is called.
_valkey: valkey_client.Redis | None = None


async def get_redis() -> valkey_client.Redis:
    """
    Return the shared Valkey connection, creating it if it doesn't exist yet.

    The function is named get_redis() to match FastAPI's Depends() convention
    and to keep compatibility with any future hosted Redis-compatible services.

    decode_responses=True tells the client to automatically decode raw bytes
    from Valkey into Python strings. Without this, you would get b"hello"
    (bytes) instead of "hello" (string).
    """
    global _valkey

    if _valkey is None:
        _valkey = valkey_client.from_url(settings.redis_url, decode_responses=True)

    return _valkey


async def close_redis() -> None:
    """
    Close the Valkey connection. Called during application shutdown.

    Cleanly closing connections ensures Valkey is not left with stale
    open sockets, which matters in production environments.
    """
    global _valkey

    if _valkey is not None:
        await _valkey.aclose()
        _valkey = None
