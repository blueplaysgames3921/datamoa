"""
Event bus — pub/sub system for real-time updates
Python backend emits events → WebSocket → Electron → Renderer
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventBus:
    """
    Lightweight async pub/sub event bus.
    Agents emit events here. WebSocket handler subscribes and forwards to frontend.
    """

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()

    def subscribe(self, event: str, callback: Callable):
        self._subscribers[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable):
        if callback in self._subscribers[event]:
            self._subscribers[event].remove(callback)

    async def emit(self, event: str, data: Any = None):
        """Emit an event to all subscribers"""
        payload = {"event": event, "data": data}
        await self._queue.put(payload)

        for callback in self._subscribers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Event handler error for {event}: {e}")

        # Also emit to wildcard subscribers
        for callback in self._subscribers.get("*", []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event, data)
                else:
                    callback(event, data)
            except Exception as e:
                logger.error(f"Wildcard handler error: {e}")

    async def get_next(self) -> dict:
        """Get next event from queue (used by WebSocket handler)"""
        return await self._queue.get()

    def emit_sync(self, event: str, data: Any = None):
        """Synchronous emit — creates task in running loop"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event, data))
        except RuntimeError:
            pass


# Singleton event bus
event_bus = EventBus()


# --- Event type constants ---
class Events:
    # Pipeline
    PIPELINE_UPDATE = "pipeline:update"
    RECORD_UPDATE = "pipeline:record:update"
    RECORD_COMPLETE = "pipeline:record:complete"
    RECORD_FAILED = "pipeline:record:failed"
    HITL_REQUEST = "pipeline:hitl:request"
    PIPELINE_PAUSED = "pipeline:paused"
    PIPELINE_RESUMED = "pipeline:resumed"

    # Agents
    AGENT_STATUS = "agent:status:update"
    AGENT_ERROR = "agent:error"

    # Config
    CONFIG_AGENT_PROGRESS = "config:agent:progress"
    CONFIG_AGENT_COMPLETE = "config:agent:complete"

    # Audit
    AUDIT_NEW_ENTRY = "audit:new:entry"

    # System
    SYSTEM_ERROR = "system:error"
    HARDWARE_DETECTED = "system:hardware:detected"
