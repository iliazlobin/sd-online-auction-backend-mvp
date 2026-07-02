"""White-box test configuration.

Uses SQLite for unit tests (fast, no Postgres needed) and mock Redis.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Required by pytest-asyncio for async fixtures."""
    return "asyncio"
