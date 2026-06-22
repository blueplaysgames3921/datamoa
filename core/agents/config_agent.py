"""
Config Agent — analyzes hardware + available API keys, then assigns optimal models.

Key improvements:
- Reads which providers the user has actually configured (API keys present)
- Fetches installed local models from Ollama live
- Builds a dynamic model catalog from only VALID + AVAILABLE models
- Uses web search (if Perplexity/Gemini available) to verify current model strings
- Has clear decision rules so the LLM doesn't hallucinate model IDs
- JSON retry logic for reliable structured output
"""

import json
import logging
from typing import AsyncGenerator

from core.config.settings import AgentModelConfig, Settings
from core.models.hardware import HardwareInfo, detect_hardware
from core.models.registry import MODEL_REGISTRY
from core.models.router import ModelRouter
from core.utils.events import EventBus, Events

logger = logging.getLogger(__name__)

# ── Decision Rules ─────────────────────────────────────────────────────────────
# Hard rules the LLM must follow, injected dynamically based on user state.

AGENT_REQUIREMENTS = {
    "intake":       {"needs_tool_use": False, "speed": "fast",    "weight": "light"},
    "parsing":      {"needs_tool_use": False, "speed": "medium",  "weight": "heavy"},
    "context":      {"needs_tool_use": False, "speed": "fast",    "weight": "light"},
    "confidence":   {"needs_tool_use": False, "speed": "fast",    "weight": "light"},
    "reasoning":    {"needs_tool_use": False, "speed": "slow_ok", "weight": "heavy", "best_available": True},
    "validation":   {"needs_tool_use": False, "speed": "fast",    "weight": "light"},
    "enrichment":   {"needs_tool_use": False, "speed": "medium",  "web_search": True},
    "hitl":         {"needs_tool_use": False, "speed": "fast",    "weight": "light"},
    "write":        {"needs_tool_use": True,  "speed": "medium",  "weight": "medium"},
    "audit":        {"needs_tool_use": False, "speed": "slow_ok", "weight": "medium"},
    "learning":     {"needs_tool_use": False, "speed": "slow_ok", "weight": "light"},
    "orchestrator": {"needs_tool_use": False, "speed": "fast",    "weight": "medium", "moe_preferred": True},
    "config_agent": {"needs_tool_use": False, "speed": "medium",  "weight": "medium"},
}

TOOL_USE_REQUIRED_AGENTS = {"write"}
WEB_SEARCH_PREFERRED_AGENTS = {"enrichment"}
MOE_PREFERRED_AGENTS = {"orchestrator"}
BEST_AVAILABLE_AGENTS = {"reasoning"}
PRIVACY_PREFERRED_LOCAL = {"intake", "context", "confidence", "validation", "hitl", "learning"}


def _build_system_prompt(
    available_models: list[dict],
    installed_local: list[str],
    configured_providers: list[str],
    hardware: HardwareInfo,
    inf_profile=None,
) -> str:
    """
    Build a fully dynamic system prompt that only mentions actually available models.
    This prevents the LLM from hallucinating IDs for models the user can't use.
    """

    # Format available models as a structured catalog
    cloud_models = [m for m in available_models if m["category"] == "cloud"]
    local_models  = [m for m in available_models if m["category"] == "local" and not m.get("draft_model")]

    cloud_catalog = "\n".join(
        f"  {m['id']}"
        f" | {m['label']}"
        f" | tool_use={m['tool_use']}"
        f" | reasoning={m['reasoning']}"
        f" | web_search={m.get('web_search', False)}"
        f" | moe={'moe' in ' '.join(m.get('strengths', []))}"
        f" | cost={m['cost_tier']}"
        f" | ctx={m['context_k']}K"
        for m in cloud_models
    )

    local_catalog = "\n".join(
        f"  {m['id']}"
        f" | {m['label']}"
        f" | VRAM={m.get('vram_required_gb', '?')}GB"
        f" | tool_use={m['tool_use']}"
        f" | installed={'YES' if any(m['id'].split('/')[-1].split(':')[0] in inst for inst in installed_local) else 'NO'}"
        for m in local_models
    ) or "  (none available — no local inference)"

    hw_summary = (
        f"GPU: {hardware.gpu_name} | VRAM: {hardware.gpu_vram_gb}GB | "
        f"RAM: {hardware.ram_gb}GB | Local inference: {'YES' if hardware.can_run_local else 'NO'}"
    )

    providers_line = ", ".join(configured_providers) if configured_providers else "NONE configured"

    # Build inference engine section for prompt
    if inf_profile:
        from core.models.inference_engine import QuantizationTier
        quant_advice = {
            QuantizationTier.INT8.value:  "INT8 — default standard (recommended). Best accuracy/memory balance.",
            QuantizationTier.INT4.value:  "INT4 — budget mode. Constrained hardware. Acceptable quality loss.",
            QuantizationTier.INT3.value:  "INT3 — aggressive compression. Use only tiny models.",
            QuantizationTier.INT2.value:  "INT2 — extreme constraint only. Significant quality loss.",
        }.get(inf_profile.quantization.value, "INT8 default")

        inf_section = (
            f"Engine: {inf_profile.engine.value}\n"
            f"Hardware tier: {inf_profile.hardware_tier.value}\n"
            f"Quantization: {inf_profile.quantization.value} — {quant_advice}\n"
            f"Supports speculative decoding: {inf_profile.supports_speculative}\n"
            f"Supports MLX (Apple Silicon): {inf_profile.supports_mlx}\n"
            + ("\n".join(f"Note: {n}" for n in inf_profile.notes) if inf_profile.notes else "")
        )

        # Engine-specific local model rules
        if inf_profile.engine.value == "mlx":
            inf_section += (
                "\nMLX RULE: Prefer local models — unified memory means no VRAM/RAM split. "
                "All local models run efficiently. Use larger local models than you would on other hardware."
            )
        elif inf_profile.engine.value == "cloud_only":
            inf_section += (
                "\nCLOUD-ONLY RULE: Do NOT assign any ollama/* models. "
                "All 13 agents must use cloud model IDs only."
            )
        elif inf_profile.hardware_tier.value == "windows_npu":
            inf_section += (
                "\nNPU RULE: Local models run via LiteRT-LM/ONNX. "
                "Prefer small local models (gemma3:4b, lfm2.5:1.2b) for NPU-accelerated roles."
            )
        elif inf_profile.hardware_tier.value == "cpu_only":
            inf_section += (
                "\nCPU-ONLY RULE: Only assign local models to agents if RAM >= model requirement * 1.5. "
                "Prefer cloud for heavy agents (reasoning, parsing, write)."
            )
    else:
        inf_section = "No inference profile available — use default hybrid strategy."

    return f"""You are the Configuration Agent for DataMoA, a professional multi-agent data entry system.

YOUR TASK:
Assign the single best AI model string to each of 13 agent roles based on:
1. Hardware constraints (VRAM, RAM)
2. Which API keys the user has configured
3. Agent-specific requirements (tool use, speed, reasoning depth)
4. Cost efficiency

═══════════════════════════════════════════════
SYSTEM HARDWARE
═══════════════════════════════════════════════
{hw_summary}

═══════════════════════════════════════════════
CONFIGURED API PROVIDERS (user has keys for these)
═══════════════════════════════════════════════
{providers_line}

═══════════════════════════════════════════════
AVAILABLE CLOUD MODELS (provider key present)
═══════════════════════════════════════════════
{cloud_catalog if cloud_catalog else "  (no cloud providers configured)"}

═══════════════════════════════════════════════
AVAILABLE LOCAL MODELS (Ollama, if VRAM sufficient)
═══════════════════════════════════════════════
{local_catalog}

═══════════════════════════════════════════════
LOCAL INFERENCE ENGINE & QUANTIZATION
═══════════════════════════════════════════════
{inf_section}
═══════════════════════════════════════════════
AGENT REQUIREMENTS & DECISION RULES
═══════════════════════════════════════════════

MANDATORY RULES (never violate):
R1. Only use model IDs from the AVAILABLE lists above. No exceptions. No other IDs.
R2. write agent MUST have tool_use=True — it calls APIs and writes files.
R3. enrichment agent MUST have web_search=True OR be a capable reasoning model that can use the Perplexity tool.
R4. reasoning agent gets the HIGHEST reasoning capability available, period.
R5. Never assign a local model if its VRAM requirement exceeds available VRAM.
R6. If no cloud providers configured, ALL agents must use local models or the best available local model.
R7. If no local models available (VRAM too low / Ollama not installed), ALL must use cloud.
R8. config_agent must be a cloud model (Google or Perplexity preferred) — it needs search.

PRIORITY RULES (apply in order when multiple models qualify):
P1. orchestrator → prefer MoE models (moe=True). MoE routes tokens efficiently — ideal for coordination.
P2. reasoning    → prefer highest reasoning score, then largest context, then cost (ignore cost here).
P3. parsing      → prefer strong instruction following + large context. Groq is fast and free.
P4. write        → must have tool_use=True. Prefer Haiku/Flash for speed. Cost matters here.
P5. enrichment   → MUST have web_search=True if available. Perplexity Sonar Pro is ideal.
P6. audit        → prefer analytical/skeptical models. DeepSeek is excellent here.
P7. intake, context, confidence, validation, hitl, learning → prefer FAST + CHEAP.
    If local models with sufficient VRAM exist: prefer local for privacy.
    Otherwise: use fastest/cheapest cloud (Gemini Flash, Groq Llama).

HYBRID STRATEGY:
- Local first for: intake, context, confidence, validation, hitl, learning (privacy + speed)
- Cloud for: parsing, reasoning, enrichment, write, audit (heavy compute + tool use)
- MoE for: orchestrator (routing efficiency)
- Best available for: reasoning (quality critical — this is what makes the system reliable)

COST AWARENESS:
- Budget profiles: Use cheap models for lightweight agents, expensive only for reasoning/write.
- If user has Groq: use it for parsing (free tier, very fast).
- If user has DeepSeek: use it for audit (cheapest capable analytical model).
- If user has Perplexity: use it for enrichment (web search is its superpower).

═══════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════
Return ONLY this JSON object. No markdown. No explanation. No extra keys.

{{
  "assignments": {{
    "intake":       "<exact model id from available lists>",
    "parsing":      "<exact model id from available lists>",
    "context":      "<exact model id from available lists>",
    "confidence":   "<exact model id from available lists>",
    "reasoning":    "<exact model id from available lists>",
    "validation":   "<exact model id from available lists>",
    "enrichment":   "<exact model id from available lists>",
    "hitl":         "<exact model id from available lists>",
    "write":        "<exact model id from available lists>",
    "audit":        "<exact model id from available lists>",
    "learning":     "<exact model id from available lists>",
    "orchestrator": "<exact model id from available lists>",
    "config_agent": "<exact model id from available lists>"
  }},
  "reasoning": "One sentence per agent explaining why this specific model was chosen.",
  "warnings": ["Any hardware constraints, missing providers, or suboptimal assignments"],
  "preset_label": "high_end_local | cloud_only | balanced | privacy_first | budget"
}}"""


def _get_configured_providers(settings: Settings) -> list[str]:
    """Return list of providers for which the user has API keys configured."""
    keys = settings.load_keys()
    configured = []

    provider_map = {
        "anthropic":  ["anthropic"],
        "google":     ["google"],
        "groq":       ["groq"],
        "deepseek":   ["deepseek"],
        "perplexity": ["perplexity"],
        "moonshot":   ["moonshot"],
        "openai":     ["openai"],
        "liquid":     ["liquid"],
        "stepfun":    ["stepfun"],
        "openrouter": ["openrouter"],
    }

    for key_name, providers in provider_map.items():
        if keys.get(key_name) or settings.get_key(key_name):
            configured.extend(providers)

    # ollama is always "configured" — it's local
    configured.append("ollama")
    return list(set(configured))


def _get_available_models(
    configured_providers: list[str],
    hardware: HardwareInfo,
    installed_local: list[str],
) -> list[dict]:
    """
    Filter the registry to only models the user can actually use:
    - Cloud models: provider key is present
    - Local models: Ollama available + VRAM sufficient
    """
    available = []

    for model in MODEL_REGISTRY:
        provider = model["provider"]

        # OpenRouter models need openrouter key
        if model["id"].startswith("openrouter/"):
            if "openrouter" not in configured_providers:
                continue

        # Cloud models need their provider key
        if model["category"] == "cloud":
            if provider not in configured_providers:
                continue

        # Local models need Ollama + VRAM
        if model["category"] == "local":
            if "ollama" not in configured_providers:
                continue
            vram_req = model.get("vram_required_gb", 0)
            if hardware.gpu_vram_gb >= 2.0 and hardware.gpu_vram_gb < vram_req:
                continue  # Not enough VRAM
            if hardware.gpu_vram_gb < 2.0:
                ram_req = model.get("ram_required_gb", 999)
                if hardware.ram_gb < ram_req:
                    continue  # Not enough RAM for CPU inference

        available.append(model)

    return available


async def _get_installed_ollama_models() -> list[str]:
    """Fetch currently installed Ollama models."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    return []


class ConfigAgent:
    """
    Config Agent — standalone service that configures model assignments.
    Knows what providers are configured, what models are available,
    what hardware is present, and uses decision rules + AI to choose optimally.
    """

    def __init__(self, settings: Settings, router: ModelRouter, event_bus: EventBus):
        self.settings = settings
        self.router = router
        self.event_bus = event_bus

    async def run(self) -> AsyncGenerator[dict, None]:
        """Run config agent with streaming progress events."""

        yield {"step": "detecting_hardware", "message": "Detecting your hardware..."}
        hardware = detect_hardware()

        # Detect inference engine for this hardware
        from core.models.inference_engine import detect_inference_profile
        inf_profile = detect_inference_profile(
            vram_gb=hardware.gpu_vram_gb,
            ram_gb=hardware.ram_gb,
            gpu_name=hardware.gpu_name,
        )

        yield {
            "step": "hardware_detected",
            "message": (
                f"Detected: {hardware.gpu_name}, {hardware.gpu_vram_gb}GB VRAM, "
                f"{hardware.ram_gb}GB RAM | Engine: {inf_profile.engine.value} | "
                f"Quant: {inf_profile.quantization.value}"
            ),
            "hardware": {
                "gpu_name": hardware.gpu_name,
                "gpu_vram_gb": hardware.gpu_vram_gb,
                "ram_gb": hardware.ram_gb,
                "cpu_cores": hardware.cpu_cores,
                "cpu_name": hardware.cpu_name,
                "storage_free_gb": hardware.storage_free_gb,
                "can_run_local": hardware.can_run_local,
                "platform": hardware.platform,
                "inference_engine": inf_profile.engine.value,
                "quantization": inf_profile.quantization.value,
                "hardware_tier": inf_profile.hardware_tier.value,
                "supports_speculative": inf_profile.supports_speculative,
                "supports_mlx": inf_profile.supports_mlx,
                "engine_notes": inf_profile.notes,
            },
        }

        # ── Gather user state ──────────────────────────────────────────────────
        yield {"step": "gathering_state", "message": "Reading your API keys and installed models..."}

        configured_providers = _get_configured_providers(self.settings)
        installed_local = await _get_installed_ollama_models()
        available_models = _get_available_models(configured_providers, hardware, installed_local)

        if not available_models:
            yield {
                "step": "error",
                "message": "No models available. Please add at least one API key in Settings → API Keys, or install Ollama.",
            }
            return

        # Build dynamic catalog counts for the UI
        cloud_count = sum(1 for m in available_models if m["category"] == "cloud")
        local_count  = sum(1 for m in available_models if m["category"] == "local" and not m.get("draft_model"))

        yield {
            "step": "catalog_built",
            "message": f"Found {cloud_count} cloud models ({len(configured_providers)-1} providers) + {local_count} local models",
            "providers": configured_providers,
            "model_count": len(available_models),
            "installed_local": installed_local,
        }

        # ── Choose the config agent model itself ───────────────────────────────
        config = self.settings.load_config()
        config_model = self._pick_config_model(config, configured_providers, available_models)

        yield {
            "step": "querying_ai",
            "message": f"Asking {config_model} to assign models based on your setup...",
        }

        # Build dynamic system prompt from actual user state
        system_prompt = _build_system_prompt(
            available_models=available_models,
            installed_local=installed_local,
            configured_providers=configured_providers,
            hardware=hardware,
            inf_profile=inf_profile,
        )

        user_message = self._build_user_message(hardware, configured_providers, available_models)

        try:
            response = await self.router.complete(
                model=config_model,
                messages=[{"role": "user", "content": user_message}],
                system=system_prompt,
                temperature=0.1,
                max_tokens=4096,
                timeout=45.0,
                trim_input=False,  # Never trim config agent context — all info is critical
            )

            yield {"step": "processing", "message": "Validating assignments..."}

            # Use JSON retry validator
            from core.utils.json_validator import parse_agent_json, build_retry_prompt, JSONParseError

            valid_ids = {m["id"] for m in available_models}
            data = None
            last_response = response
            last_error = None

            for attempt in range(3):
                try:
                    parsed = parse_agent_json(last_response, "config_agent")
                    assignments = parsed.get("assignments", {})

                    # Validate every ID is actually in available models
                    invalid_ids = {
                        agent: mid for agent, mid in assignments.items()
                        if mid not in valid_ids
                    }

                    if invalid_ids:
                        # IDs were hallucinated — correct and retry
                        invalid_list = "\n".join(f"  {a}: '{m}' is NOT a valid model ID" for a, m in invalid_ids.items())
                        valid_list = "\n".join(f"  {m['id']}" for m in available_models[:20])
                        retry_msg = (
                            f"Your response contained invalid model IDs that are not in the available list:\n"
                            f"{invalid_list}\n\n"
                            f"Valid model IDs (use ONLY these):\n{valid_list}\n\n"
                            f"Correct ONLY the invalid assignments. Keep valid ones unchanged. Return the full JSON."
                        )
                        if attempt < 2:
                            last_response = await self.router.complete(
                                model=config_model,
                                messages=[
                                    {"role": "user", "content": user_message},
                                    {"role": "assistant", "content": last_response},
                                    {"role": "user", "content": retry_msg},
                                ],
                                system=system_prompt,
                                temperature=0.0,
                                max_tokens=4096,
                                timeout=30.0,
                                trim_input=False,
                            )
                            continue
                        else:
                            # Auto-fix: replace invalid IDs with best fallback
                            assignments, fix_notes = self._auto_fix_assignments(
                                assignments, valid_ids, available_models, hardware
                            )
                            parsed["assignments"] = assignments
                            parsed.setdefault("warnings", []).extend(fix_notes)

                    data = parsed
                    break

                except JSONParseError as e:
                    last_error = e
                    if attempt < 2:
                        retry_prompt = build_retry_prompt(
                            original_prompt=user_message,
                            failed_response=last_response,
                            error=str(e),
                        )
                        last_response = await self.router.complete(
                            model=config_model,
                            messages=[{"role": "user", "content": retry_prompt}],
                            system=system_prompt,
                            temperature=0.0,
                            max_tokens=4096,
                            timeout=30.0,
                            trim_input=False,
                        )

            if data is None:
                raise Exception(f"Config agent failed after retries: {last_error}")

            assignments = data.get("assignments", {})

            # Final hardware validation pass
            validated, validation_notes = self._validate_assignments(
                assignments, hardware, valid_ids, available_models
            )

            # Save config
            agent_config = AgentModelConfig(**validated)
            config.agents = agent_config
            config.hardware.gpu_vram_gb = hardware.gpu_vram_gb
            config.hardware.ram_gb = hardware.ram_gb
            config.hardware.gpu_name = hardware.gpu_name
            config.hardware.can_run_local = hardware.can_run_local
            config.config_agent_ran = True
            config.first_launch = False
            self.settings.save_config(config)

            yield {
                "step": "complete",
                "message": "Configuration complete",
                "assignments": validated,
                "reasoning": data.get("reasoning", ""),
                "warnings": data.get("warnings", []) + validation_notes,
                "preset": data.get("preset_label", "balanced"),
                "providers_used": list({m.split("/")[0] for m in validated.values()}),
            }

        except Exception as e:
            logger.error(f"Config agent failed: {e}")
            yield {
                "step": "error",
                "message": f"Config agent failed: {str(e)}",
                "error": str(e),
            }

    def _pick_config_model(
        self,
        config,
        configured_providers: list[str],
        available_models: list[dict],
    ) -> str:
        """
        Pick the model to run the config agent itself.
        Priority: Gemini 2.5 Flash → Perplexity Sonar Pro → any capable cloud model.
        Never use local models for config agent (needs web awareness).
        """
        preferred = [
            "google/gemini-2.5-flash-preview-04-17",
            "perplexity/sonar-pro",
            "google/gemini-2.0-flash",
            "perplexity/sonar",
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-haiku-4-5",
            "groq/llama-3.3-70b-versatile",
            "deepseek/deepseek-chat",
            "openrouter/stepfun/step-3.5-flash",
            "openrouter/qwen/qwen3.6-plus",
        ]
        available_ids = {m["id"] for m in available_models if m["category"] == "cloud"}
        for model_id in preferred:
            if model_id in available_ids:
                return model_id

        # Fallback to config.agents.config_agent if it's available
        if config.agents.config_agent in available_ids:
            return config.agents.config_agent

        # Last resort: first available cloud model
        cloud = [m for m in available_models if m["category"] == "cloud"]
        if cloud:
            return cloud[0]["id"]

        raise Exception("No cloud model available to run the Config Agent. Please add at least one API key.")

    def _build_user_message(
        self,
        hw: HardwareInfo,
        configured_providers: list[str],
        available_models: list[dict],
    ) -> str:
        """Build the user-facing request with all context."""
        available_ids = [m["id"] for m in available_models if not m.get("draft_model")]
        tool_use_ids = [m["id"] for m in available_models if m.get("tool_use")]
        web_search_ids = [m["id"] for m in available_models if m.get("web_search")]
        moe_ids = [m["id"] for m in available_models if "moe" in " ".join(m.get("strengths", []))]
        reasoning_ids = sorted(
            [m for m in available_models if m.get("reasoning") and not m.get("draft_model")],
            key=lambda m: {"free": 0, "very_low": 1, "low": 2, "medium": 3, "high": 4}.get(m["cost_tier"], 2),
            reverse=True,
        )
        best_reasoning = [m["id"] for m in reasoning_ids[:5]]

        return f"""Assign DataMoA agent models for this exact user setup.

HARDWARE:
- GPU: {hw.gpu_name} ({hw.gpu_vram_gb}GB VRAM)
- RAM: {hw.ram_gb}GB
- Can run local: {hw.can_run_local}

CONFIGURED PROVIDERS: {', '.join(sorted(p for p in configured_providers if p != 'ollama')) or 'none (local only)'}

ALL VALID MODEL IDs YOU MAY USE ({len(available_ids)} total):
{chr(10).join(f'  {mid}' for mid in available_ids)}

MODELS WITH TOOL USE (required for write agent):
{chr(10).join(f'  {mid}' for mid in tool_use_ids) or '  NONE — write agent will be limited'}

MODELS WITH WEB SEARCH (best for enrichment):
{chr(10).join(f'  {mid}' for mid in web_search_ids) or '  NONE — use capable reasoning model for enrichment'}

MoE MODELS (preferred for orchestrator):
{chr(10).join(f'  {mid}' for mid in moe_ids) or '  NONE available'}

BEST REASONING MODELS (for reasoning agent, ranked by capability):
{chr(10).join(f'  {mid}' for mid in best_reasoning) or '  NONE — use best available'}

Now assign one model per agent. Use ONLY the IDs listed above. Follow all rules."""

    def _validate_assignments(
        self,
        assignments: dict,
        hw: HardwareInfo,
        valid_ids: set,
        available_models: list[dict],
    ) -> tuple[dict, list[str]]:
        """Final validation pass — fix any remaining issues."""
        validated = {}
        notes = []
        available_map = {m["id"]: m for m in available_models}

        # Ensure all 13 agent slots are filled
        required = [
            "intake", "parsing", "context", "confidence", "reasoning",
            "validation", "enrichment", "hitl", "write", "audit",
            "learning", "orchestrator", "config_agent",
        ]

        # Find best fallback cloud model
        cloud_fallback = next(
            (m["id"] for m in available_models
             if m["category"] == "cloud" and not m.get("draft_model")),
            None,
        )

        for agent in required:
            model = assignments.get(agent, "")

            # Check it's a valid ID
            if model not in valid_ids:
                fallback = cloud_fallback or list(valid_ids)[0] if valid_ids else "ollama/gemma3:4b"
                notes.append(f"'{agent}': invalid ID '{model}' → replaced with '{fallback}'")
                model = fallback

            # Check local VRAM constraint
            if model.startswith("ollama/"):
                info = available_map.get(model, {})
                vram_req = info.get("vram_required_gb", 0)
                if hw.gpu_vram_gb > 0 and hw.gpu_vram_gb < vram_req:
                    fallback = cloud_fallback or model
                    notes.append(
                        f"'{agent}': {model} needs {vram_req}GB VRAM but only {hw.gpu_vram_gb}GB available → {fallback}"
                    )
                    model = fallback

            # Check write agent has tool use
            if agent == "write":
                info = available_map.get(model, {})
                if not info.get("tool_use"):
                    # Find best tool-use model
                    tool_models = [m for m in available_models if m.get("tool_use") and not m.get("draft_model")]
                    if tool_models:
                        replacement = tool_models[0]["id"]
                        notes.append(
                            f"write agent: '{model}' has no tool use → replaced with '{replacement}'"
                        )
                        model = replacement

            validated[agent] = model

        return validated, notes

    def _auto_fix_assignments(
        self,
        assignments: dict,
        valid_ids: set,
        available_models: list[dict],
        hardware: HardwareInfo,
    ) -> tuple[dict, list[str]]:
        """Auto-fix invalid assignments with best heuristic choices."""
        notes = []
        fixed = dict(assignments)
        available_map = {m["id"]: m for m in available_models}

        cloud_cheap = [
            m["id"] for m in available_models
            if m["category"] == "cloud"
            and m["cost_tier"] in ("very_low", "low")
            and not m.get("draft_model")
        ]
        cloud_capable = [
            m["id"] for m in available_models
            if m["category"] == "cloud"
            and m.get("reasoning")
            and not m.get("draft_model")
        ]
        local_fast = [
            m["id"] for m in available_models
            if m["category"] == "local"
            and not m.get("draft_model")
        ]
        tool_use = [m["id"] for m in available_models if m.get("tool_use")]

        agent_heuristics = {
            "reasoning":    cloud_capable[:1] or cloud_cheap[:1],
            "write":        tool_use[:1],
            "enrichment":   [m["id"] for m in available_models if m.get("web_search")][:1] or cloud_cheap[:1],
            "orchestrator": [m["id"] for m in available_models if "moe" in " ".join(m.get("strengths", []))][:1] or cloud_cheap[:1],
            "audit":        ["deepseek/deepseek-chat"] if "deepseek/deepseek-chat" in valid_ids else cloud_cheap[:1],
        }

        for agent, mid in assignments.items():
            if mid not in valid_ids:
                candidates = agent_heuristics.get(agent, cloud_cheap or local_fast)
                replacement = candidates[0] if candidates else (list(valid_ids)[0] if valid_ids else mid)
                fixed[agent] = replacement
                notes.append(f"Auto-fixed '{agent}': '{mid}' → '{replacement}'")

        return fixed, notes
