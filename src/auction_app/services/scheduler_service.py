"""SchedulerService — APScheduler lifecycle driver.

Polls PostgreSQL for auctions whose start_ts or end_ts has been reached
and dispatches start_auction / close_auction calls.

Runs inside the FastAPI lifespan.  Poll interval: 1 second.
Each poll processes up to 100 auctions.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis as AsyncRedis
from sqlalchemy import select

from auction_app.database import async_session_factory
from auction_app.models.auction import Auction
from auction_app.redis_client import get_pool
from auction_app.services.auction_service import close_auction, start_auction

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
POLL_INTERVAL_SECONDS = 1


async def _get_redis() -> AsyncRedis:
    """Get a fresh Redis connection from the pool."""
    pool = get_pool()
    return AsyncRedis(connection_pool=pool)


async def poll_due_starts() -> None:
    """Start auctions whose start_ts has been reached."""
    try:
        redis = await _get_redis()
    except Exception:
        logger.exception("Failed to connect to Redis for start poll")
        return

    try:
        async with async_session_factory() as db:
            now_utc = datetime.now(UTC)
            stmt = (
                select(Auction)
                .where(
                    Auction.state == "UPCOMING",
                    Auction.start_ts <= now_utc,
                )
                .limit(BATCH_SIZE)
            )
            result = await db.execute(stmt)
            auctions = result.scalars().all()

            for auction in auctions:
                try:
                    await start_auction(db, redis, auction.auction_id)
                except Exception:
                    logger.exception(
                        "Failed to start auction %s", auction.auction_id
                    )

            await db.commit()
    except Exception:
        logger.exception("Error in poll_due_starts")
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


async def poll_due_closes() -> None:
    """Close auctions whose end_ts has been reached."""
    try:
        redis = await _get_redis()
    except Exception:
        logger.exception("Failed to connect to Redis for close poll")
        return

    try:
        async with async_session_factory() as db:
            now_utc = datetime.now(UTC)
            stmt = (
                select(Auction)
                .where(
                    Auction.state == "ACTIVE",
                    Auction.end_ts <= now_utc,
                )
                .limit(BATCH_SIZE)
            )
            result = await db.execute(stmt)
            auctions = result.scalars().all()

            for auction in auctions:
                try:
                    # Check Redis for extended end_ts (anti-snipe)
                    key = f"auction:{auction.auction_id}"
                    redis_data = await redis.hgetall(key)
                    if redis_data:
                        redis_end_ts = redis_data.get("end_ts")
                        if isinstance(redis_end_ts, bytes):
                            redis_end_ts = redis_end_ts.decode()
                        if redis_end_ts:
                            redis_end = int(float(redis_end_ts))
                            now_unix = int(now_utc.timestamp())
                            if now_unix < redis_end:
                                # Auction was extended — update DB end_ts and skip
                                auction.end_ts = datetime.fromtimestamp(
                                    redis_end, tz=UTC
                                )
                                continue

                    await close_auction(db, redis, auction.auction_id)
                except Exception:
                    logger.exception(
                        "Failed to close auction %s", auction.auction_id
                    )

            await db.commit()
    except Exception:
        logger.exception("Error in poll_due_closes")
    finally:
        try:
            await redis.aclose()
        except Exception:
            pass


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        poll_due_starts,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        id="poll_due_starts",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.add_job(
        poll_due_closes,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        id="poll_due_closes",
        replace_existing=True,
        max_instances=1,
    )

    return scheduler
