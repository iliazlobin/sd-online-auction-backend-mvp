"""AuctionService — create, lifecycle, close, settle.

Correctness-critical lifecycle transitions.  This module is the single
owner of auction state transitions (UPCOMING → ACTIVE → CLOSED → SOLD/UNSOLD).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.models.auction import Auction
from auction_app.models.user import User
from auction_app.schemas.auction import AuctionCreate, AuctionDetail

# ──────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────


def _to_decimal_str(val: Any) -> str:
    """Render a numeric value to a two-decimal string for JSON / Redis."""
    if val is None:
        return "0.00"
    return f"{float(val):.2f}"


def _ensure_str(val: Any) -> str:
    """Decode bytes → str, or just str()."""
    if isinstance(val, bytes):
        return val.decode()
    return str(val) if val is not None else ""


# ──────────────────────────────────────────────────────────────────
# AuctionService
# ──────────────────────────────────────────────────────────────────


async def create_auction(
    db: AsyncSession,
    seller_id: uuid.UUID,
    data: AuctionCreate,
    *,
    redis: AsyncRedis | None = None,
) -> Auction:
    """Create an auction row in PostgreSQL.

    Validates the seller exists, then inserts the auction.
    If the auction starts immediately (start_ts in the past),
    initializes the Redis hash.
    """
    # Verify seller exists
    seller = await db.get(User, seller_id)
    if seller is None:
        raise ValueError("seller not found")

    now_utc = datetime.now(UTC)

    # Reject start_ts too far in the past (>5 min ago)
    past_cutoff = now_utc - timedelta(minutes=5)
    if data.start_ts < past_cutoff:
        raise ValueError("start_ts too far in the past")

    # Reject end_ts <= start_ts
    if data.end_ts <= data.start_ts:
        raise ValueError("end_ts must be after start_ts")

    if data.start_ts <= now_utc:
        # Start time in the past → auction starts immediately (state ACTIVE)
        state = "ACTIVE"
    else:
        state = "UPCOMING"

    auction = Auction(
        seller_id=seller_id,
        title=data.title,
        description=data.description,
        category=data.category,
        starting_price=data.starting_price,
        reserve_price=data.reserve_price,
        min_increment=data.min_increment,
        start_ts=data.start_ts,
        end_ts=data.end_ts,
        state=state,
    )
    db.add(auction)
    await db.flush()
    await db.refresh(auction)

    # Initialize Redis hash for immediately ACTIVE auctions
    if state == "ACTIVE" and redis is not None:
        await _init_redis_hash(redis, auction)

    return auction


async def _init_redis_hash(redis: AsyncRedis, auction: Auction) -> None:
    """Initialize the Redis hash for an active auction."""
    key = f"auction:{auction.auction_id}"
    await redis.hset(
        key,
        mapping={
            "state": "ACTIVE",
            "highest_bid": "0.00",
            "highest_bidder": "",
            "end_ts": str(int(auction.end_ts.timestamp())),
            "start_ts": str(int(auction.start_ts.timestamp())),
            "sequence_num": "0",
            "extensions_used": "0",
            "min_increment": _to_decimal_str(auction.min_increment),
        },
    )


async def start_auction(
    db: AsyncSession,
    redis: AsyncRedis,
    auction_id: uuid.UUID,
) -> None:
    """Transition auction from UPCOMING → ACTIVE.

    Initialises the Redis state hash and updates the DB row.
    """
    auction = await db.get(Auction, auction_id)
    if auction is None:
        return

    # Update DB
    auction.state = "ACTIVE"

    # Initialise Redis hash
    await _init_redis_hash(redis, auction)


async def close_auction(
    db: AsyncSession,
    redis: AsyncRedis,
    auction_id: uuid.UUID,
) -> None:
    """Transition auction from ACTIVE → CLOSED.

    Reads winner info from Redis and flushes it to PostgreSQL.
    """
    auction = await db.get(Auction, auction_id)
    if auction is None:
        return

    key = f"auction:{auction_id}"
    data = await redis.hgetall(key)

    if not data:
        # Redis hash missing — just close with whatever DB has
        auction.state = "CLOSED"
        await db.flush()
        await _resolve_settlement_inner(auction)
        # Also set Redis state
        await redis.hset(key, "state", auction.state)
        return

    highest_bidder = _ensure_str(data.get("highest_bidder", ""))
    highest_bid_str = _ensure_str(data.get("highest_bid", "0"))

    auction.state = "CLOSED"

    if highest_bidder:
        auction.highest_bid = float(highest_bid_str)
        auction.winner_id = uuid.UUID(highest_bidder)

    await db.flush()
    await _resolve_settlement_inner(auction)

    # Update Redis hash to reflect the closed state
    await redis.hset(key, "state", auction.state)


async def _resolve_settlement_inner(auction: Auction) -> None:
    """Check reserve price and mark SOLD or UNSOLD."""
    if auction.state != "CLOSED":
        return

    if auction.winner_id is None:
        auction.state = "UNSOLD"
    elif auction.reserve_price is not None and auction.highest_bid is not None:
        if auction.highest_bid >= auction.reserve_price:
            auction.state = "SOLD"
        else:
            auction.state = "UNSOLD"
            auction.winner_id = None
    else:
        auction.state = "SOLD"


async def get_auction_detail(
    db: AsyncSession,
    redis: AsyncRedis,
    auction_id: uuid.UUID,
) -> AuctionDetail | None:
    """Merge PostgreSQL metadata with Redis current state into AuctionDetail."""
    auction = await db.get(Auction, auction_id)
    if auction is None:
        return None

    # Count bids
    from auction_app.models.bid import Bid

    bid_count_expr = select(Bid).where(Bid.auction_id == auction_id, Bid.status == "ACCEPTED")
    bid_result = await db.execute(bid_count_expr)
    bid_count = len(bid_result.scalars().all())

    # Try Redis for current price; fall back to DB
    key = f"auction:{auction_id}"
    redis_data = await redis.hgetall(key)

    if redis_data:
        current_price = _ensure_str(redis_data.get("highest_bid", "0"))
        state = _ensure_str(redis_data.get("state", auction.state))
        end_ts_unix = int(float(_ensure_str(redis_data.get("end_ts", "0"))))
    else:
        current_price = _to_decimal_str(auction.highest_bid or auction.starting_price)
        state = auction.state
        end_ts_unix = int(auction.end_ts.timestamp())

    now_ts = int(datetime.now(UTC).timestamp())
    time_remaining = max(0, end_ts_unix - now_ts)

    return AuctionDetail(
        auction_id=auction.auction_id,
        title=auction.title,
        category=auction.category,
        starting_price=_to_decimal_str(auction.starting_price),
        current_price=current_price,
        min_increment=_to_decimal_str(auction.min_increment),
        bid_count=bid_count,
        state=state,
        start_ts=auction.start_ts,
        end_ts=auction.end_ts,
        time_remaining_seconds=time_remaining,
        winner_id=auction.winner_id,
        reserve_price=(float(auction.reserve_price) if auction.reserve_price is not None else None),
    )
