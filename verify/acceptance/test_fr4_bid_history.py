"""
FR4: Bid History — paginated retrieval of bids for an auction.

Black-box HTTP test against the running auction API.
No app imports. Uses httpx client fixtures from conftest.py.
"""

import datetime
import uuid

import pytest


def _create_auction(client, seller, **overrides):
    """Helper: create an auction via REST. Returns JSON response dict."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "title": f"Auction {uuid.uuid4().hex[:8]}",
        "description": "FR4 acceptance test auction",
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


def test_fr4_bid_history_paginated_newest_first(client, seller, bidder):
    """FR4: GET /auctions/{id}/history returns bids newest-first with cursor pagination."""
    auction = _create_auction(client, seller)

    # Place several bids at increasing amounts (same bidder hits SELF_OUTBID on lower ones)
    amounts = [110.00, 150.00, 200.00, 250.00, 300.00]
    accepted = []
    for amt in amounts:
        r = client.post(
            f"/auctions/{auction['auction_id']}/bids",
            json={"amount": amt},
            headers={"X-User-ID": bidder["user_id"]},
        )
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("status") == "ACCEPTED":
                accepted.append(data.get("bid_id"))

    # Fetch bid history
    r = client.get(
        f"/auctions/{auction['auction_id']}/history",
        params={"limit": 3},
    )
    assert r.status_code == 200, f"GET history failed: {r.status_code} {r.text}"
    body = r.json()

    assert body["auction_id"] == auction["auction_id"]
    assert "bids" in body
    bids = body["bids"]
    assert isinstance(bids, list)
    assert len(bids) > 0, f"Expected at least one bid in history, got empty list"
    assert len(bids) <= 3, f"Limit 3 should return at most 3 bids, got {len(bids)}"

    # Verify structure of each bid entry
    first_bid = bids[0]
    for field in ("bid_id", "bidder_id", "amount", "sequence_num", "created_ts"):
        assert field in first_bid, f"Missing {field}: {first_bid}"

    # Verify newest-first ordering (sequence_num descending)
    if len(bids) >= 2:
        assert bids[0]["sequence_num"] > bids[1]["sequence_num"], (
            f"Expected newest first (descending sequence_num), "
            f"got {bids[0]['sequence_num']} then {bids[1]['sequence_num']}"
        )

    # Cursor should be present when there may be more pages
    if "next_cursor" in body:
        assert isinstance(body["next_cursor"], (int, type(None))), (
            f"next_cursor should be int or null, got {type(body['next_cursor'])}"
        )


def test_fr4_bid_history_nonexistent_auction_returns_404(client):
    """FR4: GET history on nonexistent auction returns 404."""
    fake_id = str(uuid.uuid4())
    r = client.get(f"/auctions/{fake_id}/history")
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_fr4_bid_history_empty_auction_returns_empty_list(client, seller):
    """FR4: GET history on auction with no bids returns empty list."""
    auction = _create_auction(client, seller)

    r = client.get(f"/auctions/{auction['auction_id']}/history")
    assert r.status_code == 200, f"GET history failed: {r.status_code} {r.text}"
    body = r.json()

    assert body["auction_id"] == auction["auction_id"]
    assert body["bids"] == [] or len(body["bids"]) == 0, (
        f"Expected empty bids list, got {body['bids']}"
    )
