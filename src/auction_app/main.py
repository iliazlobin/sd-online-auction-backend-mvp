"""FastAPI application factory — create_app(), lifespan, /healthz.

Alembic is the sole schema owner — no create_all() here.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from auction_app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup and teardown."""
    # ── Startup ──────────────────────────────────────────────────
    # Redis Lua script registration, scheduler start, etc.
    # These will be wired in as services are implemented.
    yield
    # ── Shutdown ─────────────────────────────────────────────────
    # Cleanup tasks (close pools, etc.)


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    app = FastAPI(
        title="Online Auction MVP",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Mount routers ────────────────────────────────────────────
    app.include_router(health_router)

    return app
