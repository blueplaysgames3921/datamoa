"""
DataMoA Model Router — optimized LiteLLM interface.

Implements:
  1. Prompt caching     — Anthropic/Google/Groq prefix caching headers
  2. Speculative decoding — Ollama draft-model support (LFM 2.5 1.2B / Gemma 4 E2B)
  3. Context trimming   — relevance-based truncation before sending to model
  4. Token budgeting    — per-agent max_tokens scaled to model context window
  5. Parallel batching  — concurrent completion for batch-eligible agents
"""

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator

import litellm
from litellm import acompletion

from core.config.settings import Settings
from core.models.inference_engine import (
    detect_inference_profile, apply_quantization_to_model_id,
    InferenceEngine, HardwareTier, QuantizationTier,
)
from core.models.warm_pool import warm_pool, TaskComplexity

logger = logging.getLogger(__name__)
litellm.set_verbose = False

# ── Draft models for speculative decoding ─────────────────────────────────────
# Key: target model name fragment → draft model to use
# Draft must be same family, much smaller, available in Ollama
SPECULATIVE_DRAFT_MODELS: dict[str, str] = {
    "gemma3:27b":       "ollama/gemma4:e2b",       # Gemma 4 E2B as draft
    "gemma3:12b":       "ollama/gemma4:e2b",
    "llama3.3:70b":     "ollama/lfm2.5:1.2b",      # LFM 2.5 1.2B as draft
    "llama3.3:8b":      "ollama/lfm2.5:1.2b",
    "qwen2.5:72b":      "ollama/gemma4:e2b",
    "qwen2.5:14b":      "ollama/gemma4:e2b",
    "mistral:7b":       "ollama/lfm2.5:1.2b",
    "phi4":             "ollama/lfm2.5:1.2b",
    # Fallback draft if nothing matches
    "_default":         "ollama/gemma4:e2b",
}

# Models that support prompt caching natively
CACHE_SUPPORTED_PROVIDERS = {"anthropic", "google", "groq"}

# Per-model context windows (tokens) — used for token budgeting
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus":       200_000,
    "claude-sonnet":     200_000,
    "claude-haiku":      200_000,
    "gemini-2.5":      1_000_000,
    "gemini-2.0":      1_000_000,
    "llama-3.3-70b":    128_000,
    "llama-3.1-8b":     128_000,
    "deepseek":          64_000,
    "gemma3:27b":       128_000,
    "gemma3:12b":       128_000,
    "gemma3:4b":        128_000,
    "gemma4:e2b":        32_000,
    "lfm2.5:1.2b":       32_000,
    "qwen2.5:72b":      128_000,
    "qwen2.5:14b":       32_000,
    "qwen2.5:7b":        32_000,
    "phi4":              16_000,
    "mistral:7b":        32_000,
}

# Lightweight agents that can run in parallel batches
PARALLELIZABLE_AGENTS = {"confidence", "validation", "context", "hitl"}


def _get_context_window(model: str) -> int:
    """Return context window size for a model."""
    model_lower = model.lower()
    for fragment, size in MODEL_CONTEXT_WINDOWS.items():
        if fragment in model_lower:
            return size
    return 32_000  # conservative default


def _get_draft_model(target_model: str) -> str | None:
    """
    Return the appropriate draft model for speculative decoding.
    Only applies to local Ollama models.
    Returns None if not applicable.
    """
    if not target_model.startswith("ollama/"):
        return None
    
    model_name = target_model.replace("ollama/", "").lower()
    
    for fragment, draft in SPECULATIVE_DRAFT_MODELS.items():
        if fragment != "_default" and fragment in model_name:
            return draft
    
    # Use default draft for any ollama model
    return SPECULATIVE_DRAFT_MODELS["_default"]


def _add_cache_headers(
    kwargs: dict,
    model: str,
    system: str | None,
    messages: list[dict],
) -> dict:
    """
    Add prompt caching headers for supported providers.
    
    Anthropic: cache_control on system prompt and first user message
    Google: automatic — no extra headers needed
    Groq: cache_control on system messages
    """
    provider = model.split("/")[0] if "/" in model else ""
    
    if provider not in CACHE_SUPPORTED_PROVIDERS:
        return kwargs
    
    if provider == "anthropic":
        # Anthropic requires cache_control on individual message blocks
        full_messages = kwargs.get("messages", [])
        updated = []
        for i, msg in enumerate(full_messages):
            if msg["role"] == "system" and isinstance(msg.get("content"), str):
                # Cache the system prompt — it's identical for every record
                updated.append({
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                })
            elif i == 1 and msg["role"] == "user":
                # Cache long user context (document text etc.)
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 1000:
                    updated.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    })
                else:
                    updated.append(msg)
            else:
                updated.append(msg)
        kwargs["messages"] = updated

    elif provider == "groq":
        # Groq uses extra_headers for caching
        kwargs.setdefault("extra_headers", {})
        kwargs["extra_headers"]["x-groq-cache"] = "true"

    # Google (Gemini) handles caching automatically via context caching API
    # No extra headers needed for standard calls

    return kwargs


def _trim_context(
    text: str,
    max_chars: int,
    preserve_start: int = 2000,
    preserve_end: int = 1000,
) -> str:
    """
    Trim text to fit within max_chars while preserving the most relevant parts.
    Keeps the start (usually headers/metadata) and end (usually totals/signatures)
    and removes the middle if needed.
    """
    if len(text) <= max_chars:
        return text
    
    middle_budget = max_chars - preserve_start - preserve_end - 50  # 50 for ellipsis marker
    
    if middle_budget <= 0:
        # Very tight budget — just take start
        return text[:max_chars - 20] + "\n\n[... truncated ...]"
    
    start = text[:preserve_start]
    end = text[-preserve_end:] if preserve_end > 0 else ""
    middle_sample = text[preserve_start: preserve_start + middle_budget]
    
    return f"{start}\n\n[... {len(text) - preserve_start - preserve_end} chars trimmed for context ...]\n\n{middle_sample}\n\n[...]\n\n{end}"


def _build_ollama_options(
    target_model: str,
    use_speculative: bool,
) -> dict:
    """
    Build Ollama-specific options for the API call.
    Includes speculative decoding draft model if applicable and available.
    """
    options: dict = {
        # Memory efficiency options for Ollama
        "num_keep": 24,           # Keep N tokens in KV cache across requests
        "low_vram": False,        # Let Ollama decide based on available VRAM
        "f16_kv": True,           # Use float16 for KV cache (half the memory vs float32)
    }
    
    if not use_speculative:
        return options
    
    draft = _get_draft_model(target_model)
    if draft:
        draft_name = draft.replace("ollama/", "")
        # Check if draft model is actually installed
        try:
            import urllib.request, json as _json
            resp = urllib.request.urlopen(
                "http://localhost:11434/api/tags", timeout=2
            )
            data = _json.loads(resp.read())
            installed = [m["name"] for m in data.get("models", [])]
            draft_available = any(
                draft_name.split(":")[0] in m for m in installed
            )
            if draft_available:
                options["draft_model"] = draft_name
                logger.debug(f"Speculative decoding: {target_model} → draft {draft_name}")
            else:
                logger.debug(
                    f"Draft model {draft_name} not installed — "
                    f"run 'ollama pull {draft_name}' to enable speculative decoding"
                )
        except Exception:
            pass  # Ollama unreachable or draft check failed — continue without

    return options


class ModelRouter:
    """
    Optimized model router with:
    - Prompt caching (Anthropic/Google/Groq)
    - Speculative decoding (Ollama local models)
    - Context window trimming
    - Token budgeting
    - Parallel batch completion
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._inject_keys()
        self._speculative_enabled: bool = True
        self._cache_enabled: bool = True
        self._inference_profile = None  # Set lazily after hardware detection
        self._quantization = QuantizationTier.INT8  # Default standard

    def _inject_keys(self):
        key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai":    "OPENAI_API_KEY",
            "google":    "GEMINI_API_KEY",
            "groq":      "GROQ_API_KEY",
            "deepseek":  "DEEPSEEK_API_KEY",
            "perplexity":"PERPLEXITY_API_KEY",
            "moonshot":  "MOONSHOT_API_KEY",
        }
        for provider, env_var in key_map.items():
            key = self.settings.get_key(provider)
            if key:
                os.environ[env_var] = key

    def refresh_keys(self):
        self._inject_keys()

    def set_speculative_decoding(self, enabled: bool):
        self._speculative_enabled = enabled

    def set_prompt_caching(self, enabled: bool):
        self._cache_enabled = enabled

    def apply_inference_profile(self, vram_gb: float, ram_gb: float, gpu_name: str = ""):
        """Detect and store the inference profile for this hardware."""
        from core.models.inference_engine import detect_inference_profile
        self._inference_profile = detect_inference_profile(vram_gb, ram_gb, gpu_name)
        self._quantization = self._inference_profile.quantization
        logger.info(
            f"Inference profile: {self._inference_profile.engine.value} | "
            f"tier={self._inference_profile.hardware_tier.value} | "
            f"quant={self._inference_profile.quantization.value}"
        )
        for note in self._inference_profile.notes:
            logger.info(f"  → {note}")
        return self._inference_profile

    def configure_warm_pool(self, agent_models: dict[str, str]):
        """Configure the warm model pool from agent assignments."""
        warm_pool.configure(agent_models)

    def get_agent_params(self, agent_name: str) -> dict:
        """Get the inference parameters for a specific agent role."""
        return warm_pool.get_inference_params(agent_name)

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
        timeout: float = 90.0,
        trim_input: bool = True,
    ) -> str:
        """
        Optimized completion with caching, speculative decoding, and context trimming.
        """
        # Validate model
        validation = self.validate_model_config(model)
        if not validation["valid"]:
            raise ModelError(model=model, message=validation["reason"])

        # Apply quantization suffix to local models based on hardware profile
        if model.startswith("ollama/") and self._inference_profile:
            model = apply_quantization_to_model_id(model, self._quantization)

        # ── 1. Token budgeting ────────────────────────────────────────────────
        ctx_window = _get_context_window(model)
        output_budget = min(max_tokens, ctx_window // 5, 8192)

        # ── 2. Context trimming ───────────────────────────────────────────────
        # Respect user setting for context trimming
        try:
            cfg = self.settings.load_config()
            do_trim = trim_input and cfg.context_trimming_enabled
        except Exception:
            do_trim = trim_input

        trimmed_messages = []
        for msg in messages:
            content_val = msg.get("content", "")
            if do_trim and isinstance(content_val, str):
                # Estimate chars budget: context_window * 3 chars/token, minus system prompt
                system_chars = len(system or "") 
                available_chars = (ctx_window * 3) - system_chars - (output_budget * 4)
                max_input_chars = max(2000, min(available_chars, 120_000))
                if len(content_val) > max_input_chars:
                    content_val = _trim_context(content_val, max_input_chars)
                    logger.debug(
                        f"[{model}] Context trimmed: {len(msg['content'])} → {len(content_val)} chars"
                    )
            trimmed_messages.append({**msg, "content": content_val})

        # ── 3. Build full message list ────────────────────────────────────────
        full_messages: list[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(trimmed_messages)

        # ── 4. Build kwargs ───────────────────────────────────────────────────
        kwargs: dict[str, Any] = {
            "model":       model,
            "messages":    full_messages,
            "temperature": temperature,
            "max_tokens":  output_budget,
            "timeout":     timeout,
        }
        if response_format:
            kwargs["response_format"] = response_format

        # ── 5. Prompt caching headers ─────────────────────────────────────────
        if self._cache_enabled:
            kwargs = _add_cache_headers(kwargs, model, system, full_messages)

        # ── 6. Speculative decoding (Ollama only) ─────────────────────────────
        if self._speculative_enabled and model.startswith("ollama/"):
            options = _build_ollama_options(model, use_speculative=True)
            if options:
                kwargs["options"] = options

        try:
            t0 = time.monotonic()
            response = await acompletion(**kwargs)
            elapsed = time.monotonic() - t0
            text = response.choices[0].message.content or ""

            # Log cache hit info if available
            usage = getattr(response, "usage", None)
            if usage:
                cached = getattr(usage, "cache_read_input_tokens", 0) or 0
                if cached > 0:
                    logger.debug(
                        f"[{model}] Cache hit: {cached} tokens cached "
                        f"({elapsed:.2f}s)"
                    )

            return text

        except litellm.AuthenticationError as e:
            logger.error(f"Auth error for model {model}: {e}")
            raise ModelAuthError(model=model, provider=model.split("/")[0]) from e
        except litellm.RateLimitError as e:
            logger.warning(f"Rate limit for model {model}: {e}")
            raise ModelRateLimitError(model=model) from e
        except litellm.ContextWindowExceededError as e:
            logger.error(f"Context window exceeded for model {model}: {e}")
            raise ModelContextError(model=model) from e
        except litellm.ServiceUnavailableError as e:
            logger.error(f"Service unavailable for model {model}: {e}")
            raise ModelUnavailableError(model=model) from e
        except Exception as e:
            logger.error(f"Unexpected error for model {model}: {e}")
            raise ModelError(model=model, message=str(e)) from e

    async def complete_batch(
        self,
        requests: list[dict],
        max_parallel: int = 8,
    ) -> list[str]:
        """
        Run multiple completions in parallel.
        Each request is a dict matching complete() kwargs.
        Used for lightweight agents (confidence, validation, context) on batch inputs.
        
        Example:
            results = await router.complete_batch([
                {"model": "ollama/gemma3:4b", "messages": [...], "system": "..."},
                {"model": "ollama/gemma3:4b", "messages": [...], "system": "..."},
            ])
        """
        semaphore = asyncio.Semaphore(max_parallel)

        async def _one(req: dict) -> str:
            async with semaphore:
                return await self.complete(**req)

        results = await asyncio.gather(
            *[_one(r) for r in requests],
            return_exceptions=True,
        )

        # Replace exceptions with empty string (caller handles gracefully)
        out = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"Batch completion {i} failed: {r}")
                out.append("")
            else:
                out.append(r)
        return out

    async def stream(
        self,
        model: str,
        messages: list[dict[str, str]],
        system: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Streaming completion — used by HITL live display."""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model":       model,
            "messages":    full_messages,
            "temperature": temperature,
            "max_tokens":  min(max_tokens, _get_context_window(model) // 5),
            "stream":      True,
        }

        if self._speculative_enabled and model.startswith("ollama/"):
            options = _build_ollama_options(model, use_speculative=True)
            if options:
                kwargs["options"] = options

        response = await acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def validate_model_config(self, model: str) -> dict:
        """Validate model is configured and reachable."""
        if not model or model == "—":
            return {"valid": False, "reason": "No model configured"}

        provider = model.split("/")[0] if "/" in model else "unknown"

        if provider == "ollama":
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:11434/api/version", timeout=1)
                return {"valid": True, "reason": "Ollama available"}
            except Exception:
                return {"valid": False, "reason": "Ollama not running. Install from https://ollama.ai"}

        key_map = {
            "anthropic": "anthropic", "google": "google", "openai": "openai",
            "groq": "groq", "deepseek": "deepseek",
            "perplexity": "perplexity", "moonshot": "moonshot",
        }
        provider_key = key_map.get(provider)
        if provider_key:
            key = self.settings.get_key(provider_key)
            if not key:
                return {
                    "valid": False,
                    "reason": f"No API key for '{provider}'. Add it in Settings → API Keys.",
                }

        return {"valid": True, "reason": ""}

    def can_run_locally(self, model: str, hardware_vram_gb: float, hardware_ram_gb: float) -> bool:
        if not model.startswith("ollama/"):
            return True

        model_name = model.replace("ollama/", "")
        vram_requirements = {
            "gemma3:4b": 3.0, "gemma4:e2b": 2.0, "lfm2.5:1.2b": 1.5,
            "gemma3:12b": 8.0, "gemma3:27b": 16.0,
            "llama3.3:70b": 40.0, "llama3.3:70b-q4": 24.0, "llama3.3:8b": 6.0,
            "qwen2.5:7b": 6.0, "qwen2.5:14b": 10.0, "qwen2.5:72b": 40.0,
            "mistral:7b": 6.0, "phi4": 10.0,
        }
        required = vram_requirements.get(model_name, 8.0)
        if hardware_vram_gb < 2.0:
            return hardware_ram_gb >= required * 1.5
        return hardware_vram_gb >= required

    def get_optimization_status(self) -> dict:
        """Return current optimization configuration."""
        return {
            "prompt_caching": self._cache_enabled,
            "speculative_decoding": self._speculative_enabled,
            "cache_supported_providers": list(CACHE_SUPPORTED_PROVIDERS),
            "draft_models": SPECULATIVE_DRAFT_MODELS,
            "inference_profile": self._inference_profile.to_dict() if self._inference_profile else None,
            "quantization": self._quantization.value if self._quantization else "int8",
            "warm_pool_slots": warm_pool.get_slot_stats(),
        }


# ── Custom exceptions ──────────────────────────────────────────────────────────

class ModelError(Exception):
    def __init__(self, model: str, message: str):
        self.model = model
        self.message = message
        super().__init__(f"[{model}] {message}")

class ModelAuthError(ModelError):
    def __init__(self, model: str, provider: str):
        self.provider = provider
        super().__init__(model=model, message=f"Authentication failed for '{provider}'. Check your API key.")

class ModelRateLimitError(ModelError):
    def __init__(self, model: str):
        super().__init__(model=model, message="Rate limit reached.")

class ModelContextError(ModelError):
    def __init__(self, model: str):
        super().__init__(model=model, message="Input too long for model context window.")

class ModelUnavailableError(ModelError):
    def __init__(self, model: str):
        super().__init__(model=model, message="Model service unavailable.")
