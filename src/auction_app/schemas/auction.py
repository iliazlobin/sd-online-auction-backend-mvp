"""Auction Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class AuctionCreate(BaseModel):
    title: str
    description: str | None = None
    category: str
    starting_price: float
    reserve_price: float | None = None
    min_increment: float = 1.00
    start_ts: datetime
    end_ts: datetime

    @field_validator("starting_price")
    @classmethod
    def starting_price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("starting_price must be > 0")
        return v

    @field_validator("min_increment")
    @classmethod
    def min_increment_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("min_increment must be > 0")
        return v


class AuctionResponse(BaseModel):
    auction_id: uuid.UUID
    seller_id: uuid.UUID
    title: str
    category: str
    starting_price: float
    reserve_price: float | None = None
    min_increment: float
    state: str
    start_ts: datetime
    end_ts: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AuctionDetail(BaseModel):
    auction_id: uuid.UUID
    title: str
    category: str
    starting_price: str
    current_price: str | None = None
    min_increment: str
    bid_count: int = 0
    state: str
    start_ts: datetime
    end_ts: datetime
    time_remaining_seconds: int

    model_config = {"from_attributes": True}
