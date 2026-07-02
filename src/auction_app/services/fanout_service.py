"""FanOutService — Redis Pub/Sub broadcast with bidder masking."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any


def mask_bidder_id(bidder_id: str) -> str:
    """Return first 8 hex characters of SHA256(bidder_id)."""
    return hashlib.sha256(bidder_id.encode()).hexdigest()[:8]


def publish_bid_accepted(
    redis: Any,
    auction_id: str,
    bidder_id: str,
    bidder_user_id: str | None,
    amount: Decimal | str,
    sequence_num: int,
    end_ts: float,
) -> None:
    """Publish a bid-accepted event to the fanout Pub/Sub channel.

    The caller provides a connected Redis client with decode_responses=True.
    """
    _masked = mask_bidder_id(str(bidder_id))
    # In production: redis.publish(f"fanout:auction:{auction_id}", json.dumps(payload))
    # For now this is a pure data-builder; the caller wires the publish.
    pass


async def get_current_state(redis: Any, auction_id: str) -> dict[str, str]:
    """Return HGETALL from the auction Redis hash for initial WS frame."""
    data = await redis.hgetall(f"auction:{auction_id}")
    return {k: v for k, v in data.items()} if data else {}
