"""
DataMoA Backend — FastAPI entry point
Handles all agent orchestration, pipeline management, and WebSocket event streaming
"""

import argparse
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.utils.logger import setup_logger
from core.utils.events import event_bus
from core.config.settings import Settings

logger = setup_logger(__name__)
settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.pipeline.orchestrator_service import OrchestratorService
    logger.info("DataMoA backend starting...")
    orchestrator = OrchestratorService(settings=settings, event_bus=event_bus)
    await orchestrator.start()
    app.state.orchestrator = orchestrator
    logger.info(f"DataMoA backend ready on port {settings.port}")

    # Start health monitor background task
    from core.utils.health_monitor import run_health_monitor
    health_task = asyncio.create_task(run_health_monitor(app, interval_seconds=10))

    # Start backup scheduler
    from core.utils.backup import BackupScheduler
    from core.config.settings import DATA_DIR
    config = settings.load_config()
    backup_scheduler = BackupScheduler(
        data_dir=DATA_DIR,
        interval_hours=config.backup_interval_hours,
    )
    if config.backup_enabled:
        backup_scheduler.start()
    app.state.backup_scheduler = backup_scheduler

    yield

    # Backup on exit if enabled
    config = settings.load_config()
    if config.backup_on_exit:
        try:
            from core.utils.backup import create_backup
            create_backup(DATA_DIR, label="exit")
            logger.info("Exit backup created")
        except Exception as e:
            logger.error(f"Exit backup failed: {e}")

    backup_scheduler.stop()
    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass
    logger.info("DataMoA backend shutting down...")
    await orchestrator.stop()


app = FastAPI(title="DataMoA", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "file://", "http://localhost:7532"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from core.api.routes.pipeline import router as pipeline_router
from core.api.routes.agents import router as agents_router
from core.api.routes.system import router as system_router
from core.api.routes.audit import router as audit_router
from core.api.routes.websocket import router as ws_router
from core.api.routes.models import router as models_router

app.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
app.include_router(agents_router, prefix="/agents", tags=["agents"])
app.include_router(system_router, prefix="/system", tags=["system"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])
app.include_router(models_router, prefix="/models", tags=["models"])
app.include_router(ws_router, tags=["websocket"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7532)
    args = parser.parse_args()

    settings.port = args.port

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
    )
