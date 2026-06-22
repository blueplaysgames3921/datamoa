"""
Agents API routes — status, model assignment, config agent
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class ModelAssignRequest(BaseModel):
    agent: str
    model: str


@router.get("/status")
async def get_status(request: Request):
    orchestrator = request.app.state.orchestrator
    return orchestrator.get_agent_status()


@router.get("/models")
async def get_models(request: Request):
    settings = request.app.state.orchestrator.settings
    config = settings.load_config()
    return config.agents.model_dump()


@router.post("/models/assign")
async def assign_model(request: Request, body: ModelAssignRequest):
    settings = request.app.state.orchestrator.settings
    config = settings.load_config()

    if not hasattr(config.agents, body.agent):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown agent: {body.agent}")

    setattr(config.agents, body.agent, body.model)
    settings.save_config(config)

    orchestrator = request.app.state.orchestrator
    # Refresh router keys in case new provider
    orchestrator.router.refresh_keys()
    # Reconfigure warm pool with updated assignments
    orchestrator.router.configure_warm_pool(config.agents.model_dump())

    return {"status": "assigned", "agent": body.agent, "model": body.model}


@router.post("/config/run")
async def run_config_agent(request: Request):
    """
    Run the config agent — streams progress via WebSocket.
    This endpoint just triggers it; progress comes through WS events.
    """
    from core.agents.config_agent import ConfigAgent
    from core.utils.events import event_bus, Events

    orchestrator = request.app.state.orchestrator
    config_agent = ConfigAgent(
        settings=orchestrator.settings,
        router=orchestrator.router,
        event_bus=event_bus,
    )

    import asyncio

    async def _run():
        async for progress in config_agent.run():
            await event_bus.emit(Events.CONFIG_AGENT_PROGRESS, progress)

    async def _run_and_reconfigure():
        async for progress in config_agent.run():
            await event_bus.emit(Events.CONFIG_AGENT_PROGRESS, progress)
            # After completion, reconfigure warm pool with new assignments
            if progress.get("step") == "complete" and progress.get("assignments"):
                orchestrator.router.configure_warm_pool(progress["assignments"])

    asyncio.create_task(_run_and_reconfigure())
    return {"status": "started"}
