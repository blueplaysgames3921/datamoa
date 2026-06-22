"""
System API routes — hardware, config, presets, Google OAuth
"""

import json
import os
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


@router.get("/hardware")
async def get_hardware():
    from core.models.hardware import detect_hardware
    hw = detect_hardware()
    return {
        "gpu_name": hw.gpu_name,
        "gpu_vram_gb": hw.gpu_vram_gb,
        "ram_gb": hw.ram_gb,
        "cpu_cores": hw.cpu_cores,
        "cpu_name": hw.cpu_name,
        "storage_free_gb": hw.storage_free_gb,
        "platform": hw.platform,
        "can_run_local": hw.can_run_local,
    }


@router.get("/config")
async def get_config(request: Request):
    settings = request.app.state.orchestrator.settings
    config = settings.load_config()
    return config.model_dump()


@router.post("/config")
async def save_config(request: Request):
    body = await request.json()
    settings = request.app.state.orchestrator.settings
    from core.config.settings import UserConfig
    try:
        config = UserConfig(**body)
        settings.save_config(config)
        # Refresh model router keys after config save
        request.app.state.orchestrator.router.refresh_keys()
        return {"status": "saved"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/presets")
async def get_presets():
    from core.config.presets import PRESETS
    return PRESETS


@router.post("/presets/{preset_id}/apply")
async def apply_preset(request: Request, preset_id: str):
    from core.config.presets import PRESETS
    from core.config.settings import AgentModelConfig, PipelineConfig

    if preset_id not in PRESETS:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found")

    settings = request.app.state.orchestrator.settings
    config = settings.load_config()
    preset = PRESETS[preset_id]

    config.agents = AgentModelConfig(**preset["agents"])
    config.pipeline = PipelineConfig(**preset["pipeline"])
    config.preset = preset_id
    settings.save_config(config)

    return {"status": "applied", "preset": preset_id}


# ─── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google/status")
async def google_oauth_status():
    """Check if Google Sheets OAuth is set up"""
    from core.config.settings import DATA_DIR
    tokens_file = DATA_DIR / "google_tokens.json"
    if tokens_file.exists():
        try:
            from core.tools.google_sheets import get_credentials
            creds = get_credentials()
            return {"authenticated": creds is not None, "token_file": str(tokens_file)}
        except Exception:
            pass
    return {"authenticated": False}


@router.get("/google/auth-url")
async def google_auth_url(request: Request):
    """Generate Google OAuth authorization URL"""
    try:
        from google_auth_oauthlib.flow import Flow
        settings = request.app.state.orchestrator.settings
        client_id = settings.get_key("google_client_id") or os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = settings.get_key("google_client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET", "")

        if not client_id or not client_secret:
            return {
                "error": "Google Client ID and Secret required. Add them via Settings → API Keys or GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET env vars.",
                "instructions": "Create OAuth credentials at https://console.cloud.google.com/apis/credentials"
            }

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost:8085"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
            redirect_uri="http://localhost:8085",
        )
        auth_url, state = flow.authorization_url(
            prompt="consent",
            access_type="offline",
        )
        return {"url": auth_url, "state": state}
    except ImportError:
        return {"error": "google-auth-oauthlib not installed. Run: pip install google-auth-oauthlib google-api-python-client"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/google/exchange-code")
async def google_exchange_code(request: Request):
    """Exchange OAuth authorization code for access + refresh tokens"""
    try:
        body = await request.json()
        code = body.get("code", "")
        if not code:
            raise HTTPException(status_code=400, detail="Authorization code required")

        settings = request.app.state.orchestrator.settings
        client_id = settings.get_key("google_client_id") or os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = settings.get_key("google_client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET", "")

        from google_auth_oauthlib.flow import Flow
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost:8085"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = Flow.from_client_config(
            client_config,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
            redirect_uri="http://localhost:8085",
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        from core.config.settings import DATA_DIR
        tokens_file = DATA_DIR / "google_tokens.json"
        with open(tokens_file, "w") as f:
            f.write(creds.to_json())

        return {"success": True, "message": "Google Sheets authenticated successfully"}
    except ImportError:
        return {"success": False, "error": "google-auth-oauthlib not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/google/revoke")
async def google_revoke():
    """Revoke Google OAuth and delete stored tokens"""
    from core.config.settings import DATA_DIR
    tokens_file = DATA_DIR / "google_tokens.json"
    if tokens_file.exists():
        tokens_file.unlink()
    return {"status": "revoked"}


# ─── API Key Management ────────────────────────────────────────────────────────

@router.get("/keys")
async def get_keys(request: Request):
    """Return masked keys — last 4 chars visible, rest hidden"""
    settings = request.app.state.orchestrator.settings
    raw = settings.load_keys()
    masked = {}
    for provider, key in raw.items():
        if key:
            masked[provider] = "••••••••••••" + key[-4:]
        else:
            masked[provider] = None
    return masked


@router.post("/keys")
async def save_key(request: Request):
    """Save an API key for a provider"""
    body = await request.json()
    provider = body.get("provider", "").strip()
    key = body.get("key", "").strip()
    if not provider or not key:
        raise HTTPException(status_code=400, detail="provider and key required")
    settings = request.app.state.orchestrator.settings
    keys = settings.load_keys()
    keys[provider] = key
    settings.save_keys(keys)
    # Refresh model router so new key is active immediately
    request.app.state.orchestrator.router.refresh_keys()
    return {"success": True, "provider": provider}


@router.delete("/keys/{provider}")
async def delete_key(request: Request, provider: str):
    """Remove an API key"""
    settings = request.app.state.orchestrator.settings
    keys = settings.load_keys()
    if provider in keys:
        del keys[provider]
        settings.save_keys(keys)
    request.app.state.orchestrator.router.refresh_keys()
    return {"success": True, "provider": provider}


# ─── Ollama ────────────────────────────────────────────────────────────────────

@router.get("/ollama/status")
async def ollama_status():
    """Check if Ollama is running"""
    from core.tools.ollama import check_ollama_running
    return await check_ollama_running()


@router.get("/ollama/models")
async def ollama_models():
    """List models available in Ollama"""
    from core.tools.ollama import list_ollama_models
    return await list_ollama_models()


@router.get("/ollama/check/{model_name:path}")
async def check_ollama_model(model_name: str):
    """Check if a specific model is available"""
    from core.tools.ollama import check_model_available
    return await check_model_available(model_name)


@router.post("/ollama/pull/{model_name:path}")
async def pull_ollama_model(model_name: str):
    """Trigger model pull — streams progress via WebSocket"""
    from core.tools.ollama import pull_model
    from core.utils.events import event_bus
    import asyncio

    async def _pull():
        async for progress in pull_model(model_name):
            await event_bus.emit("ollama:pull:progress", {
                "model": model_name,
                **progress,
            })

    asyncio.create_task(_pull())
    return {"status": "pulling", "model": model_name}


# ─── Backup Management ────────────────────────────────────────────────────────

@router.get("/backups")
async def list_backups():
    """List all available backups"""
    from core.utils.backup import list_backups as _list
    return _list()


@router.post("/backups/create")
async def create_backup_now(request: Request, label: str = "manual"):
    """Create a backup immediately"""
    from core.utils.backup import create_backup
    from core.config.settings import DATA_DIR
    result = create_backup(DATA_DIR, label=label)
    return result


@router.delete("/backups/{backup_name}")
async def delete_backup(backup_name: str):
    """Delete a specific backup"""
    from core.utils.backup import delete_backup as _delete
    success = _delete(backup_name)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"status": "deleted", "name": backup_name}


@router.post("/backups/{backup_name}/restore")
async def restore_backup(backup_name: str):
    """Restore a backup (creates safety backup first)"""
    from core.utils.backup import restore_backup as _restore
    from core.config.settings import DATA_DIR
    result = _restore(backup_name, DATA_DIR)
    return result


@router.post("/backups/schedule")
async def update_backup_schedule(request: Request):
    """Update backup schedule — takes effect immediately"""
    body = await request.json()
    hours = float(body.get("interval_hours", 24.0))
    enabled = bool(body.get("enabled", True))

    settings = request.app.state.orchestrator.settings
    config = settings.load_config()
    config.backup_interval_hours = hours
    config.backup_enabled = enabled
    settings.save_config(config)

    # Update running scheduler
    if hasattr(request.app.state, "backup_scheduler"):
        sched = request.app.state.backup_scheduler
        if enabled:
            sched.set_interval(hours)
            if not sched._running:
                sched.start()
        else:
            sched.stop()

    return {"status": "updated", "interval_hours": hours, "enabled": enabled}


@router.get("/backups/folder")
async def get_backup_folder():
    """Get the user-visible backup folder path"""
    from core.utils.backup import get_backup_root
    folder = get_backup_root()
    return {"folder": str(folder)}


# ─── Model Optimization Settings ─────────────────────────────────────────────

@router.get("/inference-profile")
async def get_inference_profile(request: Request):
    """Get the current hardware inference profile"""
    orchestrator = request.app.state.orchestrator
    profile = orchestrator.router._inference_profile
    if profile:
        return profile.to_dict()
    # Run detection if not yet done
    from core.models.hardware import detect_hardware
    from core.models.inference_engine import detect_inference_profile
    hw = detect_hardware()
    p = detect_inference_profile(hw.gpu_vram_gb, hw.ram_gb, hw.gpu_name)
    return p.to_dict()


@router.get("/optimization")
async def get_optimization(request: Request):
    """Get current model optimization settings"""
    orchestrator = request.app.state.orchestrator
    config = orchestrator.settings.load_config()
    router_status = orchestrator.router.get_optimization_status()
    return {
        "speculative_decoding_enabled": config.speculative_decoding_enabled,
        "prompt_caching_enabled": config.prompt_caching_enabled,
        "context_trimming_enabled": config.context_trimming_enabled,
        "parallel_batch_window_ms": config.parallel_batch_window_ms,
        "router": router_status,
    }


@router.post("/optimization")
async def update_optimization(request: Request):
    """Update model optimization settings — takes effect immediately"""
    body = await request.json()
    orchestrator = request.app.state.orchestrator
    config = orchestrator.settings.load_config()

    if "speculative_decoding_enabled" in body:
        config.speculative_decoding_enabled = bool(body["speculative_decoding_enabled"])
        orchestrator.router.set_speculative_decoding(config.speculative_decoding_enabled)

    if "prompt_caching_enabled" in body:
        config.prompt_caching_enabled = bool(body["prompt_caching_enabled"])
        orchestrator.router.set_prompt_caching(config.prompt_caching_enabled)

    if "context_trimming_enabled" in body:
        config.context_trimming_enabled = bool(body["context_trimming_enabled"])

    if "parallel_batch_window_ms" in body:
        config.parallel_batch_window_ms = max(0, int(body["parallel_batch_window_ms"]))

    orchestrator.settings.save_config(config)
    return {"status": "updated", "config": {
        "speculative_decoding_enabled": config.speculative_decoding_enabled,
        "prompt_caching_enabled": config.prompt_caching_enabled,
        "context_trimming_enabled": config.context_trimming_enabled,
        "parallel_batch_window_ms": config.parallel_batch_window_ms,
    }}
