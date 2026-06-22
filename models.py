"""Model registry API route — exposes available models to the frontend"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/registry")
async def get_registry():
    from core.models.registry import get_registry
    return get_registry()


@router.get("/registry/agent/{agent_name}")
async def get_models_for_agent(agent_name: str):
    from core.models.registry import get_models_for_agent
    return get_models_for_agent(agent_name)


@router.get("/registry/compatible")
async def get_compatible(vram_gb: float = 0.0, ram_gb: float = 0.0):
    from core.models.registry import get_compatible_local_models
    return get_compatible_local_models(vram_gb, ram_gb)
