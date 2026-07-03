"""
Acceptance test helpers — black-box HTTP tests for Online Auction MVP.

Talks to the running system over HTTP via API_BASE_URL.
No app imports — this is the fixed functional contract.
"""

import os
import uuid

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8010")


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the running auction API."""
    return API_BASE_URL


@pytest.fixture(scope="session")
def client(base_url: str) -> httpx.Client:
    """Session-scoped HTTP client with base URL."""
    with httpx.Client(base_url=base_url, timeout=10.0) as c:
        yield c


@pytest.fixture
def fresh_user(client: httpx.Client) -> dict:
    """Create a unique user for a test and return the user dict."""
    name = f"test-user-{uuid.uuid4().hex[:8]}"
    email = f"{name}@example.com"
    r = client.post("/users", json={"display_name": name, "email": email})
    assert r.status_code == 201, f"User creation failed: {r.text}"
    return r.json()


@pytest.fixture
def seller(client: httpx.Client) -> dict:
    """Create a seller user for a test."""
    name = f"seller-{uuid.uuid4().hex[:8]}"
    email = f"{name}@example.com"
    r = client.post("/users", json={"display_name": name, "email": email})
    assert r.status_code == 201, f"Seller creation failed: {r.text}"
    return r.json()


@pytest.fixture
def bidder(client: httpx.Client) -> dict:
    """Create a bidder user for a test."""
    name = f"bidder-{uuid.uuid4().hex[:8]}"
    email = f"{name}@example.com"
    r = client.post("/users", json={"display_name": name, "email": email})
    assert r.status_code == 201, f"Bidder creation failed: {r.text}"
    return r.json()


def create_auction(client: httpx.Client, seller: dict, **overrides) -> dict:
    """Helper: create an auction with sensible defaults."""
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "title": f"Auction {uuid.uuid4().hex[:8]}",
        "description": "Test auction for acceptance suite",
        "category": "electronics",
        "starting_price": 100.00,
        "min_increment": 10.00,
        "start_ts": (now - datetime.timedelta(minutes=1)).isoformat(),
        "end_ts": (now + datetime.timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    r = client.post(
        "/auctions",
        json=payload,
        headers={"X-User-ID": seller["user_id"]},
    )
    assert r.status_code in (200, 201), f"Auction creation failed: {r.text}"
    return r.json()
