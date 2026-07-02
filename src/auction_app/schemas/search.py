"""Search Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchParams(BaseModel):
    category: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    q: str | None = None
    state: str = Field(default="ACTIVE", description="UPCOMING, ACTIVE, CLOSED, SOLD")
    cursor: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    auction_id: str
    title: str
    category: str
    current_price: str | None = None
    state: str
    start_ts: str
    end_ts: str
    bid_count: int = 0

    model_config = {"from_attributes": True}


class SearchResult(BaseModel):
    auctions: list[SearchResultItem]
    next_cursor: str | None = None
    total: int
