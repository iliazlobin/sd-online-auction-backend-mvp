"""Bid ORM model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auction_app.database import Base


class Bid(Base):
    __tablename__ = "bid"

    bid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    auction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    bidder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    is_proxy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sequence_num: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACCEPTED",
        server_default="ACCEPTED",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
    )

    # Relationships
    auction = relationship("Auction", back_populates="bids")
    bidder = relationship("User", back_populates="bids")

    def __repr__(self) -> str:
        return f"<Bid {self.amount} on {self.auction_id} ({self.status})>"
