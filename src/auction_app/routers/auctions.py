"""Auction router — CRUD + bid history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.database import get_session
from auction_app.redis_client import get_redis
from auction_app.schemas.auction import AuctionCreate, AuctionDetail, AuctionResponse
from auction_app.schemas.bid import BidHistoryPage
from auction_app.services.auction_service import (
    create_auction,
    get_auction_detail,
)
from auction_app.services.bid_service import get_bid_history

router = APIRouter(prefix="/auctions", tags=["auctions"])


def _parse_user_id(x_user_id: str | None) -> uuid.UUID:
    """Parse X-User-ID header into a UUID, or raise 400."""
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-ID header")
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-User-ID format")


@router.post("", status_code=201, response_model=AuctionResponse)
async def create_auction_route(
    data: AuctionCreate,
    x_user_id: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_session),
    redis: AsyncRedis = Depends(get_redis),
) -> AuctionResponse:
    """Create a new auction listing."""
    seller_id = _parse_user_id(x_user_id)
    try:
        auction = await create_auction(db, seller_id, data, redis=redis)
    except ValueError as e:
        detail = str(e)
        if "not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
    return AuctionResponse.model_validate(auction)


@router.get("/{auction_id}", response_model=AuctionDetail)
async def view_auction(
    auction_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    redis: AsyncRedis = Depends(get_redis),
) -> AuctionDetail:
    """View auction details, including current price from Redis."""
    detail = await get_auction_detail(db, redis, auction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Auction not found")
    return detail


@router.get("/{auction_id}/history", response_model=BidHistoryPage)
async def bid_history(
    auction_id: uuid.UUID,
    cursor: Annotated[int | None, Query(description="sequence_num to paginate from")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: AsyncSession = Depends(get_session),
) -> BidHistoryPage:
    """Paginated bid history, newest-first."""
    page = await get_bid_history(db, auction_id, cursor=cursor, limit=limit)
    if page is None:
        raise HTTPException(status_code=404, detail="Auction not found")
    return page
