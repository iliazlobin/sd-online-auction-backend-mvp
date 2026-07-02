"""Search router — GET /auctions (search/filter)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auction_app.database import get_session
from auction_app.schemas.search import SearchResult
from auction_app.services.search_service import search_auctions

router = APIRouter(tags=["search"])


@router.get("/auctions", response_model=SearchResult)
async def search_auctions_route(
    category: Annotated[str | None, Query()] = None,
    price_min: Annotated[float | None, Query()] = None,
    price_max: Annotated[float | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    state: Annotated[str, Query()] = "ACTIVE",
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_session),
) -> SearchResult:
    """Search active auctions with optional filters."""
    return await search_auctions(
        db,
        category=category,
        price_min=price_min,
        price_max=price_max,
        q=q,
        state=state,
        cursor=cursor,
        limit=limit,
    )
