"""Application configuration via pydantic-settings.

All environment-driven configuration lives here.  Safe local-dev defaults
point at compose-service hostnames (db / redis).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, env-driven configuration for the auction app."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── PostgreSQL ──────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://auction:auction@db:5432/auction"

    # ── Redis ───────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── App ──────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()
