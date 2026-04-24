"""Redis access layer.

Exposes a shared `get_redis` dependency for FastAPI and a Lua-based token
bucket for rate limiting. Using Lua ensures atomicity — read-modify-write
on the counter + expiry happens server-side in one hop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import redis.asyncio as aioredis

from app.core.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Module-level singleton — Redis connections are cheap to share."""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            str(settings.redis_url),
            decode_responses=True,
            max_connections=50,
            health_check_interval=30,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Rate limit token bucket ─────────────────────────────
# Atomic CAS: returns 1 if allowed, 0 if rate-limited.
# Arguments: key, max_tokens, refill_per_sec, cost, now_ms
RATE_LIMIT_LUA = """
local key = KEYS[1]
local max_tokens   = tonumber(ARGV[1])
local refill_rate  = tonumber(ARGV[2])     -- tokens per second
local cost         = tonumber(ARGV[3])
local now_ms       = tonumber(ARGV[4])

local bucket = redis.call('HMGET', key, 'tokens', 'last')
local tokens = tonumber(bucket[1])
local last   = tonumber(bucket[2])

if tokens == nil then
  tokens = max_tokens
  last   = now_ms
end

-- refill
local elapsed = (now_ms - last) / 1000.0
tokens = math.min(max_tokens, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tokens, 'last', now_ms)
-- TTL = enough to fully refill + slack, so idle buckets disappear.
redis.call('PEXPIRE', key, math.ceil((max_tokens / refill_rate) * 1000) + 2000)

return { allowed, math.floor(tokens) }
"""


class RateLimiter:
    """Token bucket rate limiter keyed by an arbitrary identity string."""

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._script = redis.register_script(RATE_LIMIT_LUA)

    async def check(
        self,
        identity: str,
        *,
        max_tokens: int | None = None,
        per_minute: int | None = None,
        cost: int = 1,
    ) -> tuple[bool, int]:
        """Returns (allowed, remaining_tokens)."""
        max_t = max_tokens or settings.rate_limit_burst
        per_m = per_minute or settings.rate_limit_per_minute
        refill = per_m / 60.0
        import time
        now_ms = int(time.time() * 1000)
        result = await self._script(
            keys=[f"rl:{identity}"],
            args=[max_t, refill, cost, now_ms],
        )
        allowed_raw, remaining_raw = result
        return bool(int(allowed_raw)), int(remaining_raw)
