"""
WebSocket route — streams all pipeline events to the Electron frontend in real time
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.utils.events import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

# Active WebSocket connections
_connections: set[WebSocket] = set()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    logger.info(f"WebSocket connected. Total connections: {len(_connections)}")

    # Subscribe to all events
    async def on_event(event: str, data):
        try:
            await websocket.send_text(json.dumps({
                "event": event,
                "data": data,
            }, default=str))
        except Exception:
            pass

    event_bus.subscribe("*", on_event)

    try:
        # Send initial state immediately on connect
        await websocket.send_text(json.dumps({
            "event": "connection:established",
            "data": {"status": "connected"},
        }))

        # Keep connection alive — client messages are control signals
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle ping/pong
                if msg == "ping":
                    await websocket.send_text(json.dumps({"event": "pong"}))
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text(json.dumps({"event": "keepalive"}))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _connections.discard(websocket)
        event_bus.unsubscribe("*", on_event)


async def broadcast(event: str, data):
    """Broadcast an event to all connected clients"""
    dead = set()
    for ws in _connections:
        try:
            await ws.send_text(json.dumps({"event": event, "data": data}, default=str))
        except Exception:
            dead.add(ws)
    _connections -= dead
