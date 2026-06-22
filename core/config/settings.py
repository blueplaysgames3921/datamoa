"""
DataMoA Settings — Pydantic-based configuration management
All user settings, model assignments, and API keys managed here
"""

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings


# --- Data directory (local persistent storage) ---
DATA_DIR = Path(os.environ.get("DATAMOA_DATA_DIR", Path.home() / ".datamoa"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
KEYS_FILE = DATA_DIR / "keys.json"
MEMORY_DIR = DATA_DIR / "memory"
AUDIT_DIR = DATA_DIR / "audit"
QUEUE_DIR = DATA_DIR / "queue"

for d in [MEMORY_DIR, AUDIT_DIR, QUEUE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# --- Agent model assignments ---
class AgentModelConfig(BaseModel):
    intake: str = "ollama/gemma3:4b"
    parsing: str = "groq/llama-3.3-70b-versatile"
    context: str = "ollama/gemma3:4b"
    confidence: str = "ollama/gemma3:4b"
    reasoning: str = "anthropic/claude-opus-4-6"
    validation: str = "ollama/gemma3:4b"
    enrichment: str = "perplexity/sonar"
    hitl: str = "ollama/gemma3:4b"
    write: str = "anthropic/claude-haiku-4-5"
    audit: str = "deepseek/deepseek-chat"
    learning: str = "ollama/gemma3:4b"
    orchestrator: str = "google/gemini-2.5-flash"
    config_agent: str = "google/gemini-2.5-flash"


# --- Pipeline settings ---
class PipelineConfig(BaseModel):
    max_concurrent_records: int = 5
    confidence_green_threshold: float = 0.85
    confidence_amber_threshold: float = 0.60
    auto_write_on_green: bool = True
    hitl_queue_max: int = 50
    retry_max_attempts: int = 3
    retry_delay_seconds: float = 2.0
    # Feature flags — which agents are active
    enrichment_enabled: bool = True
    context_enabled: bool = True
    learning_enabled: bool = True
    audit_batch_enabled: bool = True


# --- Hardware profile ---
class HardwareProfile(BaseModel):
    gpu_vram_gb: float = 0.0
    ram_gb: float = 0.0
    cpu_cores: int = 0
    storage_gb: float = 0.0
    gpu_name: str = "Unknown"
    can_run_local: bool = False


# --- Write destinations ---
class WriteDestination(BaseModel):
    id: str
    type: str  # csv | google_sheets | airtable | database | api
    name: str
    config: dict[str, Any] = {}
    enabled: bool = True
    field_mapping: dict[str, str] = {}  # source_field -> destination_field
    exclude_fields: list[str] = []      # fields to never write


# --- Full user config ---
class UserConfig(BaseModel):
    agents: AgentModelConfig = AgentModelConfig()
    pipeline: PipelineConfig = PipelineConfig()
    hardware: HardwareProfile = HardwareProfile()
    destinations: list[WriteDestination] = []
    preset: str = "balanced"
    first_launch: bool = True
    config_agent_ran: bool = False
    theme: str = "dark"
    backup_interval_hours: float = 24.0
    backup_enabled: bool = True
    backup_on_exit: bool = True
    # Model optimization settings
    speculative_decoding_enabled: bool = True
    prompt_caching_enabled: bool = True
    context_trimming_enabled: bool = True
    parallel_batch_window_ms: int = 50


class Settings(BaseSettings):
    port: int = 7532
    debug: bool = False

    def load_config(self) -> UserConfig:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    data = json.load(f)
                return UserConfig(**data)
            except Exception:
                pass
        return UserConfig()

    def save_config(self, config: UserConfig) -> None:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config.model_dump(), f, indent=2)

    def load_keys(self) -> dict[str, str]:
        if KEYS_FILE.exists():
            try:
                with open(KEYS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_keys(self, keys: dict[str, str]) -> None:
        with open(KEYS_FILE, "w") as f:
            json.dump(keys, f, indent=2)

    def get_key(self, provider: str) -> str | None:
        keys = self.load_keys()
        # Also check environment variables as fallback
        env_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "google": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
        }
        return keys.get(provider) or os.environ.get(env_map.get(provider, ""), None)

    class Config:
        env_prefix = "DATAMOA_"
