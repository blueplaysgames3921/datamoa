"""
System health monitor — emits periodic stats and health events via WebSocket
Runs as a background task in the FastAPI lifespan
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


async def run_health_monitor(app, interval_seconds: int = 10):
    """
    Background task that broadcasts system health every N seconds.
    Emits: pipeline stats, memory usage, agent status summary.
    """
    import psutil
    from core.utils.events import event_bus
    from core.pipeline.state import RecordStage

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            if not hasattr(app.state, 'orchestrator'):
                continue

            orchestrator = app.state.orchestrator
            records = list(orchestrator._records.values())

            # Pipeline stats
            stats = {
                "total": len(records),
                "active": sum(1 for r in records if r.stage not in (
                    RecordStage.COMPLETE, RecordStage.FAILED, RecordStage.CANCELLED
                )),
                "complete": sum(1 for r in records if r.stage == RecordStage.COMPLETE),
                "failed": sum(1 for r in records if r.stage == RecordStage.FAILED),
                "hitl": sum(1 for r in records if r.stage == RecordStage.HITL),
                "paused": orchestrator._paused,
            }

            # System resources
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=None)

            health = {
                "stats": stats,
                "system": {
                    "cpu_pct": cpu,
                    "ram_used_gb": round(mem.used / 1024**3, 1),
                    "ram_total_gb": round(mem.total / 1024**3, 1),
                    "ram_pct": mem.percent,
                },
                "timestamp": time.time(),
            }

            # Include warm pool stats
            from core.models.warm_pool import warm_pool
            health["warm_pool"] = warm_pool.get_slot_stats()

            await event_bus.emit("system:health", health)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Health monitor error: {e}")
