"""SearchService — PostgreSQL full-text search over active auctions.

Supports category filter, price range, keyword query, cursor pagination.
Uses PostgreSQL tsvector + GIN index for FTS.
"""

from __future__ import annotations

import base64
import json

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import literal_column

from auction_app.models.auction import Auction
from auction_app.schemas.search import SearchResult, SearchResultItem


def _encode_cursor(created_at: str, auction_id: str) -> str:
    """Base64-encode a (created_at, auction_id) cursor."""
    payload = json.dumps([created_at, auction_id])
    return base64.b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    """Decode a base64 cursor → (created_at, auction_id)."""
    try:
        payload = base64.b64decode(cursor.encode()).decode()
        parts = json.loads(payload)
        if len(parts) == 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None


def _build_where(stmt, *, category, price_min, price_max, q, state, cursor):
    """Apply filters to a statement and return the modified statement."""
    allowed_states = {"UPCOMING", "ACTIVE", "CLOSED", "SOLD", "UNSOLD"}
    if state in allowed_states:
        stmt = stmt.where(Auction.state == state)
    else:
        stmt = stmt.where(Auction.state == "ACTIVE")

    if category:
        stmt = stmt.where(Auction.category == category)

    if price_min is not None:
        stmt = stmt.where(
            func.coalesce(Auction.highest_bid, Auction.starting_price) >= price_min
        )
    if price_max is not None:
        stmt = stmt.where(
            func.coalesce(Auction.highest_bid, Auction.starting_price) <= price_max
        )

    if q and q.strip():
        tsquery = func.plainto_tsquery(literal_column("'english'"), q)
        tsvector = func.to_tsvector(
            literal_column("'english'"),
            Auction.title + " " + func.coalesce(Auction.description, ""),
        )
        stmt = stmt.where(tsvector.op("@@")(tsquery))

    if cursor:
        decoded = _decode_cursor(cursor)
        if decoded:
            cursor_created, cursor_id = decoded
            stmt = stmt.where(
                literal_column(
                    "(auction.created_at, auction.auction_id::text) < (:ct, :cid)"
                ).bindparams(ct=cursor_created, cid=cursor_id)
            )

    return stmt


async def search_auctions(
    db: AsyncSession,
    *,
    category: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    q: str | None = None,
    state: str = "ACTIVE",
    cursor: str | None = None,
    limit: int = 20,
) -> SearchResult:
    """Search active auctions with optional filters and full-text search."""
    limit = min(limit, 100)
    limit = max(limit, 1)

    # Build base query with filters
    base_stmt = select(Auction)
    filtered_stmt = _build_where(
        base_stmt,
        category=category,
        price_min=price_min,
        price_max=price_max,
        q=q,
        state=state,
        cursor=cursor,
    )

    # Total count — rebuild the WHERE on a count query
    count_stmt = select(func.count()).select_from(Auction)
    count_stmt = _build_where(
        count_stmt,
        category=category,
        price_min=price_min,
        price_max=price_max,
        q=q,
        state=state,
        cursor=None,  # no cursor on count
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Order by created_at DESC, auction_id DESC for stable pagination
    filtered_stmt = filtered_stmt.order_by(
        desc(Auction.created_at), desc(Auction.auction_id)
    )

    # Fetch with limit + 1 for has_more detection
    filtered_stmt = filtered_stmt.limit(limit + 1)
    result = await db.execute(filtered_stmt)
    auctions = result.scalars().all()

    has_more = len(auctions) > limit
    if has_more:
        auctions = auctions[:limit]

    items = [
        SearchResultItem(
            auction_id=str(a.auction_id),
            title=a.title,
            category=a.category,
            current_price=(
                f"{float(a.highest_bid):.2f}"
                if a.highest_bid is not None
                else f"{float(a.starting_price):.2f}"
            ),
            state=a.state,
            start_ts=a.start_ts.isoformat(),
            end_ts=a.end_ts.isoformat(),
            bid_count=0,
        )
        for a in auctions
    ]

    next_cursor = None
    if has_more and auctions:
        last = auctions[-1]
        next_cursor = _encode_cursor(
            last.created_at.isoformat(), str(last.auction_id)
        )

    return SearchResult(
        auctions=items,
        next_cursor=next_cursor,
        total=total,
    )
