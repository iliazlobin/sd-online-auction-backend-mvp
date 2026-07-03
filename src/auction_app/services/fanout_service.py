"""FanOutService — Redis Pub/Sub broadcast with bidder masking.

Broadcasts bid events to WebSocket watchers via Redis Pub/Sub.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def mask_bidder_id(bidder_id: str) -> str:
    """Return first 8 hex characters of SHA256(bidder_id)."""
    return hashlib.sha256(bidder_id.encode()).hexdigest()[:8]


async def publish_bid_accepted(
    redis: Any,
    auction_id: str,
    bidder_id: str,
    amount: str,
    sequence_num: int,
    end_ts: str,
) -> None:
    """Publish a bid-accepted event to the fanout Pub/Sub channel."""
    payload = json.dumps(
        {
            "sequence_num": sequence_num,
            "current_price": amount,
            "high_bidder_masked": mask_bidder_id(str(bidder_id)),
            "end_ts": str(end_ts),
        }
    )
    await redis.publish(f"fanout:auction:{auction_id}", payload)


async def get_current_state(redis: Any, auction_id: str) -> dict[str, str]:
    """Return HGETALL from the auction Redis hash for initial WS frame."""
    data = await redis.hgetall(f"auction:{auction_id}")
    if not data:
        return {}
    # Decode bytes keys/values if necessary
    return {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in data.items()
    }
