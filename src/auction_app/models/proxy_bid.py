"""ProxyBid ORM model — store-only proxy_max, no auto-counter in MVP."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from auction_app.database import Base


class ProxyBid(Base):
    __tablename__ = "proxy_bid"

    proxy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default="gen_random_uuid()",
    )
    auction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    bidder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    max_bid: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    entered_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default="now()",
    )

    # Relationships
    auction = relationship("Auction", back_populates="proxy_bids")
    bidder = relationship("User", back_populates="proxy_bids")

    def __repr__(self) -> str:
        return f"<ProxyBid max={self.max_bid} on {self.auction_id}>"
