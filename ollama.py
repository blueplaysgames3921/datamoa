"""
Ollama connection checker — verifies Ollama is running and a model is available
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = "http://localhost:11434"


async def check_ollama_running() -> dict:
    """Check if Ollama is running and return version info"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/version")
            if resp.status_code == 200:
                return {"running": True, "version": resp.json().get("version", "unknown")}
            return {"running": False, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"running": False, "error": "Ollama not running. Install from https://ollama.ai"}
    except Exception as e:
        return {"running": False, "error": str(e)}


async def list_ollama_models() -> list[dict]:
    """List all models available in Ollama"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return [
                    {
                        "name": m["name"],
                        "size_gb": round(m.get("size", 0) / 1024**3, 1),
                        "modified": m.get("modified_at", ""),
                    }
                    for m in models
                ]
            return []
    except Exception:
        return []


async def check_model_available(model_name: str) -> dict:
    """
    Check if a specific model is available in Ollama.
    model_name should be the short name (e.g. 'gemma3:4b', not 'ollama/gemma3:4b')
    """
    models = await list_ollama_models()
    available_names = [m["name"] for m in models]

    # Exact match or prefix match (e.g. 'gemma3:4b' matches 'gemma3:4b-instruct-q4_0')
    clean = model_name.replace("ollama/", "")
    is_available = any(
        name == clean or name.startswith(clean.split(":")[0])
        for name in available_names
    )

    return {
        "available": is_available,
        "model": model_name,
        "installed_models": available_names,
        "pull_command": f"ollama pull {clean}" if not is_available else None,
    }


async def pull_model(model_name: str):
    """
    Pull a model via Ollama API (streaming).
    Yields progress dicts.
    """
    clean = model_name.replace("ollama/", "")
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": clean},
            ) as resp:
                import json
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            yield json.loads(line)
                        except Exception:
                            yield {"status": line}
    except Exception as e:
        yield {"status": "error", "error": str(e)}
