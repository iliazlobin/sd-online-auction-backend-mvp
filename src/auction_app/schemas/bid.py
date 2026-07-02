"""Bid Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class BidRequest(BaseModel):
    amount: float
    is_proxy: bool = False
    proxy_max: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v


class BidResponse(BaseModel):
    bid_id: uuid.UUID
    status: str
    sequence_num: int | None = None
    current_price: str | None = None


class BidHistoryItem(BaseModel):
    bid_id: uuid.UUID
    bidder_id: uuid.UUID
    amount: str
    sequence_num: int
    created_ts: datetime

    model_config = {"from_attributes": True}


class BidHistoryPage(BaseModel):
    auction_id: uuid.UUID
    bids: list[BidHistoryItem]
    next_cursor: int | None = None
