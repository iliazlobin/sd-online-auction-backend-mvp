"""Auction ORM model — with tsvector FTS column."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auction_app.database import Base


class Auction(Base):
    __tablename__ = "auction"

    auction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    starting_price: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    reserve_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    min_increment: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=1.00, server_default="1.00"
    )
    start_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="UPCOMING",
        server_default="UPCOMING",
        index=True,
    )
    highest_bid: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
    )

    # Relationships
    seller = relationship("User", back_populates="auctions", foreign_keys=[seller_id])
    bids = relationship("Bid", back_populates="auction")
    proxy_bids = relationship("ProxyBid", back_populates="auction")

    def __repr__(self) -> str:
        return f"<Auction {self.title} ({self.state})>"
