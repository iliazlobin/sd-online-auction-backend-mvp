"""Bid router — POST /auctions/{id}/bids."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.database import get_session
from auction_app.redis_client import get_redis
from auction_app.schemas.bid import BidRequest
from auction_app.services.bid_service import place_bid

router = APIRouter(tags=["bids"])


def _parse_user_id(x_user_id: str | None) -> uuid.UUID:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-ID header")
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-User-ID format")


@router.post("/auctions/{auction_id}/bids")
async def place_bid_route(
    auction_id: uuid.UUID,
    data: BidRequest,
    x_user_id: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_session),
    redis: AsyncRedis = Depends(get_redis),
) -> Any:
    """Place a bid on an auction."""
    bidder_id = _parse_user_id(x_user_id)

    result = await place_bid(
        redis=redis,
        db=db,
        auction_id=auction_id,
        bidder_id=bidder_id,
        amount=data.amount,
        is_proxy=data.is_proxy,
        proxy_max=data.proxy_max,
    )

    reason = str(result.get("reason") or "")

    # Map Lua rejection reasons to appropriate HTTP responses
    if result["status"] == "REJECTED":
        if reason == "AUCTION_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Auction not found")
        if reason == "LUA_SCRIPT_ERROR":
            raise HTTPException(status_code=500, detail="Bid evaluation failed")

        # All other rejection reasons → 409 Conflict with flat body
        return JSONResponse(
            status_code=409,
            content={
                "status": "REJECTED",
                "reason": reason if reason else "UNKNOWN",
                "current_price": str(result.get("current_price", "0")),
            },
        )

    # ACCEPTED → 201
    return JSONResponse(
        status_code=201,
        content={
            "bid_id": result["bid_id"],
            "status": "ACCEPTED",
            "sequence_num": result["sequence_num"],
            "current_price": result["current_price"],
        },
    )
