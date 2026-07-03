"""WebSocket router — WS /auctions/{id}/live.

Clients connect, receive an initial state frame, then receive
real-time bid updates via Redis Pub/Sub.
"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from auction_app.redis_client import get_pool
from auction_app.services.fanout_service import mask_bidder_id

router = APIRouter(tags=["websocket"])


@router.websocket("/auctions/{auction_id}/live")
async def auction_live(websocket: WebSocket, auction_id: uuid.UUID) -> None:
    """WebSocket endpoint for real-time auction updates."""
    await websocket.accept()

    pool = get_pool()
    from redis.asyncio import Redis as AsyncRedis

    redis = AsyncRedis(connection_pool=pool)
    pubsub = redis.pubsub()

    try:
        # 1. Send initial state frame
        key = f"auction:{auction_id}"
        data = await redis.hgetall(key)

        if data:

            def _s(k: bytes | str) -> str:
                return k.decode() if isinstance(k, bytes) else k

            initial = {
                "sequence_num": int(_s(data.get("sequence_num", "0"))),
                "current_price": _s(data.get("highest_bid", "0.00")),
                "high_bidder_masked": mask_bidder_id(_s(data.get("highest_bidder", "")))
                if data.get("highest_bidder")
                else "",
                "end_ts": _s(data.get("end_ts", "0")),
            }
        else:
            initial = {
                "sequence_num": 0,
                "current_price": "0.00",
                "high_bidder_masked": "",
                "end_ts": "0",
            }

        await websocket.send_json(initial)

        # 2. Subscribe to fanout channel
        channel = f"fanout:auction:{auction_id}"
        await pubsub.subscribe(channel)

        # 3. Relay messages to WebSocket
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    data_str = message["data"]
                    if isinstance(data_str, bytes):
                        data_str = data_str.decode()
                    payload = json.loads(data_str)
                    await websocket.send_json(payload)
                except Exception:
                    pass

            # Check if client disconnected
            try:
                await asyncio.sleep(0)
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await pubsub.unsubscribe()
        except Exception:
            pass
        try:
            await redis.aclose()
        except Exception:
            pass
