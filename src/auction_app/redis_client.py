"""Async Redis client & connection pool.

Provides a get_redis dependency and a place to register Lua scripts
via SCRIPT LOAD at startup.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.connection import ConnectionPool

from auction_app.config import settings

# Lua script SHA cache — populated at startup via register_scripts()
_lua_sha: dict[str, str] = {}


def _create_pool() -> ConnectionPool:
    return ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=20,
        decode_responses=True,
    )


_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    """Return the singleton connection pool."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = _create_pool()
    return _pool


async def get_redis() -> AsyncGenerator[AsyncRedis, None]:  # type: ignore[type-arg]
    """FastAPI dependency yielding an async Redis client."""
    r: AsyncRedis[bytes] | None = None  # type: ignore[type-arg]
    try:
        r = AsyncRedis(connection_pool=get_pool())
        yield r
    finally:
        if r is not None:
            await r.aclose()


async def register_scripts(redis: AsyncRedis) -> dict[str, str]:  # type: ignore[type-arg]
    """Load Lua scripts into Redis and return {name: sha}."""
    # ── place_bid.lua ────────────────────────────────────────────
    # Full script defined in docs/system-design.md § "Redis Lua CAS Script"
    place_bid_lua = """
local h = redis.call

-- 0. Dedup: return cached result if already processed
local cached = redis.call('GET', KEYS[2])
if cached then
    if cached == 'ACCEPTED' then
        return {1, h('HGET', KEYS[1], 'highest_bid'), h('HGET', KEYS[1], 'sequence_num')}
    else
        return {0, cached}
    end
end

-- 1. State check
local state = h('HGET', KEYS[1], 'state')
if state ~= 'ACTIVE' then
    h('SET', KEYS[2], 'AUCTION_NOT_ACTIVE', 'EX', ARGV[5])
    return {0, 'AUCTION_NOT_ACTIVE'}
end

-- 2. Time check
local end_ts = tonumber(h('HGET', KEYS[1], 'end_ts'))
local now = tonumber(ARGV[4])
if now >= end_ts then
    h('SET', KEYS[2], 'AUCTION_ENDED', 'EX', ARGV[5])
    return {0, 'AUCTION_ENDED'}
end

-- 3. Amount check
local current = tonumber(h('HGET', KEYS[1], 'highest_bid') or 0)
local min_inc = tonumber(h('HGET', KEYS[1], 'min_increment'))
local min_bid = current + min_inc
local amount = tonumber(ARGV[3])

-- Self-outbid check
local current_bidder = h('HGET', KEYS[1], 'highest_bidder')
if current_bidder == ARGV[2] and amount <= current then
    h('SET', KEYS[2], 'SELF_OUTBID', 'EX', ARGV[5])
    return {0, 'SELF_OUTBID'}
end

if amount < min_bid then
    h('SET', KEYS[2], 'BID_TOO_LOW', 'EX', ARGV[5])
    return {0, 'BID_TOO_LOW'}
end

-- 4. Accept bid
h('HSET', KEYS[1], 'highest_bid', ARGV[3], 'highest_bidder', ARGV[2], 'last_bid_ts', ARGV[4])
local seq = h('HINCRBY', KEYS[1], 'sequence_num', 1)

-- 5. Anti-snipe extension (max 5 x 60s)
local ext_window = 60
local max_ext = 5
if (end_ts - now) < ext_window then
    local ext_used = tonumber(h('HGET', KEYS[1], 'extensions_used') or 0)
    if ext_used < max_ext then
        local new_end = end_ts + ext_window
        h('HSET', KEYS[1], 'end_ts', new_end, 'extensions_used', ext_used + 1)
    end
end

-- 6. Mark dedup
h('SET', KEYS[2], 'ACCEPTED', 'EX', ARGV[5])
return {1, ARGV[3], seq, h('HGET', KEYS[1], 'end_ts')}
"""

    sha = await redis.script_load(place_bid_lua)
    _lua_sha["place_bid"] = sha
    return _lua_sha


def get_lua_sha(name: str) -> str:
    """Return cached SHA for a registered Lua script."""
    return _lua_sha[name]
