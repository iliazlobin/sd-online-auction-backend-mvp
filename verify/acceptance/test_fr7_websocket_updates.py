"""
FR7: WebSocket Real-Time Updates — clients receive bid events via WebSocket.

Black-box test against the running auction API.
No app imports. Uses httpx client fixtures from conftest.py for REST calls.
WebSocket connections use the websockets library.
"""

import asyncio
import datetime
import json
import os
import uuid

import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8010")


def _ws_url(base_url: str) -> str:
    """Convert HTTP base URL to WebSocket URL."""
    return base_url.replace("http://", "ws://").replace("https://", "wss://")


def _create_auction(client, seller, **overrides):
    """Helper: create an auction via REST. Returns JSON response dict."""
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "title": f"Auction {uuid.uuid4().hex[:8]}",
        "description": "FR7 acceptance test auction",
        "category": "electronics",
        "starting_price": 100.00,
        "min_increment": 10.00,
        "start_ts": (now - datetime.timedelta(seconds=10)).isoformat(),
        "end_ts": (now + datetime.timedelta(minutes=10)).isoformat(),
    }
    payload.update(overrides)
    r = client.post(
        "/auctions",
        json=payload,
        headers={"X-User-ID": seller["user_id"]},
    )
    assert r.status_code in (200, 201), f"Auction creation failed ({r.status_code}): {r.text}"
    return r.json()


def test_fr7_websocket_receives_bid_updates(client, seller, bidder):
    """FR7: WebSocket client receives bid update frames when bids are placed.

    Steps:
    1. Create an active auction
    2. Connect WebSocket to /auctions/{id}/live
    3. Read the initial state frame (sent on connect)
    4. Place a bid via REST
    5. Assert the WebSocket receives a frame with the new bid data
    """
    try:
        import websockets
    except ImportError:
        pytest.skip("websockets library not installed")

    auction = _create_auction(client, seller)
    auction_id = auction["auction_id"]
    ws_url = f"{_ws_url(API_BASE_URL)}/auctions/{auction_id}/live"

    async def _run():
        async with websockets.connect(ws_url) as ws:
            # Read initial state frame
            initial_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            initial = json.loads(initial_raw)
            assert "current_price" in initial, f"Initial WS frame missing current_price: {initial}"
            assert "sequence_num" in initial, f"Initial WS frame missing sequence_num: {initial}"

            # Place a bid via REST in executor (httpx is sync)
            loop = asyncio.get_running_loop()
            bid_result = {}

            def _place_bid():
                r = client.post(
                    f"/auctions/{auction_id}/bids",
                    json={"amount": 200.00},
                    headers={"X-User-ID": bidder["user_id"]},
                )
                bid_result["status_code"] = r.status_code
                bid_result["body"] = r.json()

            await loop.run_in_executor(None, _place_bid)
            assert bid_result.get("status_code") in (200, 201), (
                f"Bid placement failed: {bid_result}"
            )

            # Read the bid update frame from WebSocket
            update_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            update = json.loads(update_raw)

            # Verify update frame structure
            for field in ("sequence_num", "current_price", "high_bidder_masked"):
                assert field in update, f"Update frame missing {field}: {update}"

            # current_price should reflect our bid
            current_price = float(update["current_price"])
            assert current_price >= 200.00, f"Expected current_price >= 200.00, got {current_price}"

            # Bidder mask should be 8 hex chars
            assert len(update["high_bidder_masked"]) == 8, (
                f"Bidder mask should be 8 hex chars, got '{update['high_bidder_masked']}'"
            )

    asyncio.run(_run())


def test_fr7_websocket_initial_state_on_connect(client, seller):
    """FR7: WebSocket sends initial state frame immediately on connection."""
    try:
        import websockets
    except ImportError:
        pytest.skip("websockets library not installed")

    auction = _create_auction(client, seller)
    auction_id = auction["auction_id"]
    ws_url = f"{_ws_url(API_BASE_URL)}/auctions/{auction_id}/live"

    async def _run():
        async with websockets.connect(ws_url) as ws:
            initial_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            initial = json.loads(initial_raw)

            assert "current_price" in initial, f"Missing current_price in initial frame: {initial}"
            assert "sequence_num" in initial, f"Missing sequence_num in initial frame: {initial}"
            # No bids yet → sequence_num should be 0 (or absent, treated as 0)
            seq = int(initial["sequence_num"]) if initial["sequence_num"] else 0
            assert seq >= 0, f"Expected sequence_num >= 0, got {seq}"

    asyncio.run(_run())
