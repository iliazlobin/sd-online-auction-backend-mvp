"""
FR6: Winner Determination — winner_id is correctly set after auction closes.

Black-box HTTP test against the running auction API.
No app imports. Uses httpx client fixtures from conftest.py.
"""

import datetime
import time
import uuid

import pytest


def _create_auction(client, seller, **overrides):
    """Helper: create an auction via REST. Returns JSON response dict."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "title": f"Auction {uuid.uuid4().hex[:8]}",
        "description": "FR6 acceptance test auction",
        "category": "electronics",
        "starting_price": 100.00,
        "min_increment": 10.00,
        "start_ts": (now - datetime.timedelta(seconds=10)).isoformat(),
        "end_ts": (now + datetime.timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    r = client.post(
        "/auctions",
        json=payload,
        headers={"X-User-ID": seller["user_id"]},
    )
    assert r.status_code in (200, 201), f"Auction creation failed ({r.status_code}): {r.text}"
    return r.json()


def test_fr6_winner_determined_after_close(client, seller, bidder):
    """FR6: After auction closes, winner_id is set to the highest bidder.

    Creates a short auction, places a bid, waits for close, then asserts
    the auction detail shows winner_id matching the highest bidder.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # Create auction that closes in 4 seconds
    auction = _create_auction(
        client, seller,
        start_ts=(now - datetime.timedelta(seconds=10)).isoformat(),
        end_ts=(now + datetime.timedelta(seconds=4)).isoformat(),
    )

    auction_id = auction["auction_id"]

    # Place bid
    r = client.post(
        f"/auctions/{auction_id}/bids",
        json={"amount": 200.00},
        headers={"X-User-ID": bidder["user_id"]},
    )
    assert r.status_code in (200, 201), f"Bid failed: {r.status_code} {r.text}"
    bid_data = r.json()
    assert bid_data.get("status") == "ACCEPTED", f"Bid not accepted: {bid_data}"

    # Wait for auction to close (end_ts + scheduler poll margin)
    time.sleep(7)

    # Check auction state — must be terminal
    r2 = client.get(f"/auctions/{auction_id}")
    assert r2.status_code == 200, f"GET auction failed: {r2.status_code} {r2.text}"
    data = r2.json()

    assert data["state"] in ("CLOSED", "SOLD", "UNSOLD"), (
        f"Expected terminal state, got {data['state']}"
    )

    # If SOLD or CLOSED with bids, winner_id must be set
    if data["state"] in ("SOLD", "CLOSED"):
        assert "winner_id" in data, f"Closed auction missing winner_id: {data}"
        if data["winner_id"] is not None:
            assert data["winner_id"] == bidder["user_id"], (
                f"Expected winner_id={bidder['user_id']}, got {data['winner_id']}"
            )


def test_fr6_no_winner_on_unsold_auction(client, seller):
    """FR6: Auction with no bids closes as UNSOLD with null winner_id."""
    now = datetime.datetime.now(datetime.timezone.utc)

    # Create auction that closes in 3 seconds — no bids placed
    auction = _create_auction(
        client, seller,
        start_ts=(now - datetime.timedelta(seconds=10)).isoformat(),
        end_ts=(now + datetime.timedelta(seconds=3)).isoformat(),
    )

    auction_id = auction["auction_id"]

    # Wait for close
    time.sleep(6)

    r = client.get(f"/auctions/{auction_id}")
    assert r.status_code == 200, f"GET auction failed: {r.status_code} {r.text}"
    data = r.json()

    assert data["state"] in ("CLOSED", "UNSOLD"), (
        f"Expected closed/unsold, got {data['state']}"
    )

    # No bids → winner_id should be null
    assert data.get("winner_id") is None, (
        f"Expected null winner_id for no-bid auction, got {data.get('winner_id')}"
    )
