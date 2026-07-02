"""Health-check router — GET /healthz."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe. Returns 200 when the app is up."""
    return {"status": "ok"}
