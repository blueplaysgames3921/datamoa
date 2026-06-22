"""
DataMoA Settings — Pydantic-based configuration management
All user settings, model assignments, and API keys managed here
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


# --- Data directory (local persistent storage) ---
DATA_DIR = Path(os.environ.get("DATAMOA_DATA_DIR", Path.home() / ".datamoa"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
KEYS_FILE = DATA_DIR / "keys.json"
# Symmetric key used to encrypt KEYS_FILE at rest (see _get_fernet below).
# Deliberately a separate file from keys.json itself — anyone who only gets
# a copy of keys.json (e.g. a stray backup, a misconfigured sync folder)
# gets ciphertext, not API keys.
KEYS_KEY_FILE = DATA_DIR / ".keys.key"
MEMORY_DIR = DATA_DIR / "memory"
AUDIT_DIR = DATA_DIR / "audit"
QUEUE_DIR = DATA_DIR / "queue"

for d in [MEMORY_DIR, AUDIT_DIR, QUEUE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, data: Any, default=None) -> None:
    """
    Write JSON to `path` atomically.

    `save_config`/`save_keys` (and the orchestrator's record/queue
    persistence) previously wrote directly to the target file with
    `open(path, "w")`. If the process is killed (crash, force-quit, power
    loss) partway through that write, the file is left truncated or
    otherwise invalid. The next load would then hit a JSONDecodeError —
    for config/keys this is caught and silently treated as "no config",
    discarding the user's entire saved configuration (API keys, model
    assignments, destinations, etc.) with no warning; for a pipeline
    record it would simply be unreadable on restore.

    Writing to a temp file in the same directory and then `os.replace`-ing
    it into place is atomic on both POSIX and Windows: the target file is
    always either the old complete version or the new complete version,
    never a partial write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=default)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        # If something went wrong before the replace, don't leave a stray
        # temp file behind.
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Same atomicity guarantee as _atomic_write_json, for raw bytes (used
    for the encrypted keys.json blob, which isn't itself a JSON document
    once encrypted — it's a Fernet token)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _get_or_create_fernet_key() -> bytes:
    """
    Get the symmetric key used to encrypt keys.json at rest, generating it
    on first use.

    This protects against the common cases of someone getting a copy of
    keys.json in isolation (a stray backup, a misconfigured cloud-sync
    folder, etc.) without also getting KEYS_KEY_FILE — they get an opaque
    encrypted blob, not your API keys. It does NOT protect against an
    attacker with full read access to your user account/home directory,
    since the key necessarily lives on the same disk to allow the app to
    decrypt keys without prompting for a master password on every launch.
    For protection against that threat model, rely on full-disk encryption
    and your OS user account security.
    """
    if KEYS_KEY_FILE.exists():
        return KEYS_KEY_FILE.read_bytes()

    key = Fernet.generate_key()
    _atomic_write_bytes(KEYS_KEY_FILE, key)
    try:
        # Restrict to owner-read/write only. No-op-ish on Windows, but
        # harmless there and meaningful on POSIX systems.
        os.chmod(KEYS_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def _get_fernet() -> Fernet:
    return Fernet(_get_or_create_fernet_key())


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
        _atomic_write_json(CONFIG_FILE, config.model_dump())

    def load_keys(self) -> dict[str, str]:
        if not KEYS_FILE.exists():
            return {}
        try:
            raw = KEYS_FILE.read_bytes()
        except OSError as e:
            logger.error(f"Failed to read keys file: {e}")
            return {}

        # Current format: Fernet-encrypted JSON.
        try:
            decrypted = _get_fernet().decrypt(raw)
            return json.loads(decrypted)
        except InvalidToken:
            pass
        except Exception as e:
            logger.error(f"Unexpected error decrypting keys file: {e}")

        # Backward compatibility: keys.json from a version of DataMoA that
        # predates at-rest encryption was stored as plain JSON. If
        # decryption failed, check whether this is actually that legacy
        # plaintext format — if so, transparently migrate it to encrypted
        # storage instead of silently discarding the user's saved keys.
        try:
            legacy = json.loads(raw)
            if isinstance(legacy, dict):
                logger.warning(
                    "keys.json was in the legacy plain-text format; "
                    "migrating it to encrypted storage."
                )
                self.save_keys(legacy)
                return legacy
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        # Most likely cause at this point: KEYS_KEY_FILE (.keys.key) is
        # missing or doesn't match this keys.json — e.g. a backup of
        # keys.json was restored without its matching key file, or the key
        # file was deleted. There's no way to recover the original keys
        # without it, so surface this clearly rather than pretending
        # nothing is configured.
        logger.error(
            "keys.json could not be decrypted and isn't valid legacy "
            "plain-text JSON either. This usually means the encryption "
            "key file (.keys.key) is missing or doesn't match — for "
            "example, after restoring a backup of keys.json without also "
            "restoring .keys.key. Returning no keys; you will need to "
            "re-enter your API keys in Settings."
        )
        return {}

    def save_keys(self, keys: dict[str, str]) -> None:
        payload = json.dumps(keys).encode("utf-8")
        encrypted = _get_fernet().encrypt(payload)
        _atomic_write_bytes(KEYS_FILE, encrypted)

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
