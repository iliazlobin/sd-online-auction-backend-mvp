"""BidService — atomic bid placement via Redis Lua CAS, persistence, history.

The hot-path service.  Evaluates bids via the atomic Lua CAS script,
persists accepted/rejected bids to PostgreSQL, and publishes fan-out events.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.models.auction import Auction
from auction_app.models.bid import Bid
from auction_app.models.proxy_bid import ProxyBid
from auction_app.redis_client import get_lua_sha
from auction_app.schemas.bid import BidHistoryItem, BidHistoryPage

# ──────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────


def _to_decimal_str(val: Any) -> str:
    if val is None:
        return "0.00"
    return f"{float(val):.2f}"


# ──────────────────────────────────────────────────────────────────
# place_bid
# ──────────────────────────────────────────────────────────────────


async def place_bid(
    redis: AsyncRedis,
    db: AsyncSession,
    auction_id: uuid.UUID,
    bidder_id: uuid.UUID,
    amount: float,
    is_proxy: bool = False,
    proxy_max: float | None = None,
) -> dict[str, Any]:
    """Evaluate and place a bid atomically via the Redis Lua CAS script.

    Returns a dict with at least: bid_id, status, reason (if rejected),
    current_price, sequence_num.
    """
    bid_id = uuid.uuid4()
    now_ts = time.time()
    auction_key = f"auction:{auction_id}"
    dedup_key = f"bid_result:{bid_id}"

    # Check auction exists in DB
    auction = await db.get(Auction, auction_id)
    if auction is None:
        return {
            "bid_id": str(bid_id),
            "status": "REJECTED",
            "reason": "AUCTION_NOT_FOUND",
            "current_price": None,
            "sequence_num": None,
        }

    # Compute dedup TTL: time until auction end + 48h
    end_ts_unix = auction.end_ts.timestamp()
    ttl = max(3600, int(end_ts_unix - now_ts) + 48 * 3600)

    amount_str = _to_decimal_str(amount)

    # 1. XADD to bid stream (durable record before CAS)
    try:
        await redis.xadd(
            f"auction:{auction_id}:bids",
            {
                "bid_id": str(bid_id),
                "bidder_id": str(bidder_id),
                "amount": amount_str,
                "is_proxy": "1" if is_proxy else "0",
                "client_ts": str(int(now_ts)),
            },
            maxlen=10000,
        )
    except Exception:
        # Stream not critical for correctness; proceed
        pass

    # 2. EVALSHA the Lua CAS script
    lua_sha = get_lua_sha("place_bid")
    try:
        result = await redis.evalsha(
            lua_sha,
            2,
            auction_key,
            dedup_key,
            str(bid_id),
            str(bidder_id),
            amount_str,
            str(int(now_ts)),
            str(ttl),
        )
    except Exception:
        # Fallback: try EVAL with full script (if SHA not loaded)
        # For now, return an error
        return {
            "bid_id": str(bid_id),
            "status": "REJECTED",
            "reason": "LUA_SCRIPT_ERROR",
            "current_price": None,
            "sequence_num": None,
        }

    # Parse Lua result: {status, ...}
    # status=1 → accepted, status=0 → rejected with reason string
    if not result or len(result) < 2:
        return {
            "bid_id": str(bid_id),
            "status": "REJECTED",
            "reason": "UNKNOWN_ERROR",
            "current_price": None,
            "sequence_num": None,
        }

    status_code = int(result[0])
    status = "ACCEPTED" if status_code == 1 else "REJECTED"

    if status == "ACCEPTED":
        current_price = str(result[1])
        sequence_num = int(result[2]) if len(result) > 2 else 0
        reason = None
    else:
        reason = str(result[1]) if len(result) > 1 else "UNKNOWN"
        # Get current price from Redis for rejected bids
        hash_data = await redis.hgetall(auction_key)
        current_price = hash_data.get("highest_bid", "0.00") if hash_data else "0.00"
        if isinstance(current_price, bytes):
            current_price = current_price.decode()
        sequence_num = int(hash_data.get("sequence_num", "0") or 0) if hash_data else 0

    # 3. Persist to PostgreSQL
    now_dt = datetime.now(UTC)
    bid_row = Bid(
        bid_id=bid_id,
        auction_id=auction_id,
        bidder_id=bidder_id,
        amount=amount,
        is_proxy=is_proxy,
        sequence_num=sequence_num,
        status=status,
        rejection_reason=reason,
        created_ts=now_dt,
    )
    db.add(bid_row)
    await db.flush()

    # 4. If proxy bid, store it
    if is_proxy and proxy_max is not None:
        # Upsert: one proxy per bidder per auction
        from sqlalchemy import select as sa_select

        existing = await db.execute(
            sa_select(ProxyBid).where(
                ProxyBid.auction_id == auction_id,
                ProxyBid.bidder_id == bidder_id,
            )
        )
        existing_proxy = existing.scalar_one_or_none()
        if existing_proxy:
            existing_proxy.max_bid = proxy_max
            existing_proxy.active = True
        else:
            proxy_bid = ProxyBid(
                auction_id=auction_id,
                bidder_id=bidder_id,
                max_bid=proxy_max,
                active=True,
            )
            db.add(proxy_bid)
        await db.flush()

    # 5. Publish fanout event on acceptance
    if status == "ACCEPTED":
        try:
            payload = json.dumps(
                {
                    "sequence_num": sequence_num,
                    "current_price": current_price,
                    "high_bidder_masked": _mask_bidder(str(bidder_id)),
                    "end_ts": str(int(end_ts_unix)),
                }
            )
            await redis.publish(f"fanout:auction:{auction_id}", payload)
        except Exception:
            pass

    return {
        "bid_id": str(bid_id),
        "status": status,
        "reason": reason,
        "current_price": current_price,
        "sequence_num": sequence_num,
    }


def _mask_bidder(bidder_id: str) -> str:
    """Return first 8 hex chars of SHA256(bidder_id)."""
    import hashlib

    return hashlib.sha256(bidder_id.encode()).hexdigest()[:8]


# ──────────────────────────────────────────────────────────────────
# get_bid_history
# ──────────────────────────────────────────────────────────────────


async def get_bid_history(
    db: AsyncSession,
    auction_id: uuid.UUID,
    cursor: int | None = None,
    limit: int = 50,
) -> BidHistoryPage | None:
    """Return paginated bid history for an auction, newest-first."""
    # Verify auction exists
    auction = await db.get(Auction, auction_id)
    if auction is None:
        return None

    limit = min(limit, 100)
    limit = max(limit, 1)

    stmt = select(Bid).where(
        Bid.auction_id == auction_id,
        Bid.status == "ACCEPTED",
    )

    if cursor is not None:
        stmt = stmt.where(Bid.sequence_num < cursor)

    stmt = stmt.order_by(desc(Bid.sequence_num)).limit(limit + 1)

    result = await db.execute(stmt)
    bids = result.scalars().all()

    has_more = len(bids) > limit
    if has_more:
        bids = bids[:limit]

    bid_items = [
        BidHistoryItem(
            bid_id=b.bid_id,
            bidder_id=b.bidder_id,
            amount=_to_decimal_str(b.amount),
            sequence_num=b.sequence_num,
            created_ts=b.created_ts,
        )
        for b in bids
    ]

    next_cursor = None
    if has_more and bids:
        next_cursor = bids[-1].sequence_num

    return BidHistoryPage(
        auction_id=auction_id,
        bids=bid_items,
        next_cursor=next_cursor,
    )
