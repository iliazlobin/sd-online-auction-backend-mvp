"""FastAPI application factory — create_app(), lifespan, /healthz.

Alembic is the sole schema owner — no create_all() here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis as AsyncRedis

from auction_app.redis_client import get_pool, register_scripts

logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup and teardown."""
    global _scheduler

    # ── Startup ──────────────────────────────────────────────────
    # Register Lua scripts in Redis
    pool = get_pool()
    redis = AsyncRedis(connection_pool=pool)
    try:
        await redis.ping()
        await register_scripts(redis)
        logger.info("Redis Lua scripts registered")
    except Exception as exc:
        logger.warning("Redis not available at startup: %s", exc)
    finally:
        await redis.aclose()

    # Start APScheduler
    from auction_app.services.scheduler_service import create_scheduler

    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("APScheduler started")

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler shut down")


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    app = FastAPI(
        title="Online Auction MVP",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Mount routers ────────────────────────────────────────────
    from auction_app.routers.auctions import router as auctions_router
    from auction_app.routers.bids import router as bids_router
    from auction_app.routers.health import router as health_router
    from auction_app.routers.search import router as search_router
    from auction_app.routers.users import router as users_router
    from auction_app.routers.websocket import router as websocket_router

    app.include_router(health_router)
    app.include_router(users_router)
    app.include_router(auctions_router)
    app.include_router(bids_router)
    app.include_router(search_router)
    app.include_router(websocket_router)

    return app
