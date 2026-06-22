"""
Inference Engine Detector — determines the optimal local inference backend
based on OS, hardware tier, and model architecture.

Maps:
  Windows + Copilot+ NPU     → LiteRT-LM / ONNX Runtime / OpenVINO / DirectML
  Windows + Dedicated GPU    → Ollama (CUDA/ROCm auto-detected)
  Windows + Integrated/CPU   → llama.cpp (AVX2/AVX-512)
  macOS + Apple Silicon      → MLX
  Linux + Dedicated GPU      → Ollama (CUDA/ROCm)
  Linux + CPU only           → llama.cpp

Also determines:
  - Optimal quantization tier (INT8 default, INT4 budget, INT3/INT2 extreme)
  - Whether speculative decoding is viable
  - Which warm model pool strategy to use
"""

import logging
import platform
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class InferenceEngine(str, Enum):
    OLLAMA     = "ollama"        # Best for GPU on all platforms
    MLX        = "mlx"           # Best for Apple Silicon
    LITERT_LM  = "litert_lm"    # Best for Windows NPU (Copilot+)
    LLAMA_CPP  = "llama_cpp"    # Best for CPU / legacy hardware
    CLOUD_ONLY = "cloud_only"   # No viable local engine


class QuantizationTier(str, Enum):
    BF16   = "bf16"    # Avoid unless explicitly chosen — overkill
    FP16   = "fp16"    # Same — not default
    INT8   = "int8"    # DEFAULT STANDARD — best accuracy/memory balance
    INT4   = "int4"    # Budget / constrained hardware
    INT3   = "int3"    # Ultra-low resource
    INT2   = "int2"    # Extreme compression only


class HardwareTier(str, Enum):
    APPLE_SILICON      = "apple_silicon"       # M1–M4 unified memory
    WINDOWS_NPU        = "windows_npu"         # Copilot+ / AI PC
    DEDICATED_GPU      = "dedicated_gpu"       # NVIDIA RTX / AMD Radeon
    INTEGRATED_GPU     = "integrated_gpu"      # Intel/AMD iGPU
    CPU_ONLY           = "cpu_only"            # No GPU
    CLOUD_ONLY         = "cloud_only"          # No local inference viable


@dataclass
class InferenceProfile:
    engine: InferenceEngine
    hardware_tier: HardwareTier
    quantization: QuantizationTier
    vram_gb: float
    ram_gb: float
    supports_speculative: bool
    supports_mlx: bool
    recommended_ollama_options: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine.value,
            "hardware_tier": self.hardware_tier.value,
            "quantization": self.quantization.value,
            "vram_gb": self.vram_gb,
            "ram_gb": self.ram_gb,
            "supports_speculative": self.supports_speculative,
            "supports_mlx": self.supports_mlx,
            "recommended_ollama_options": self.recommended_ollama_options,
            "notes": self.notes,
        }


def _is_apple_silicon() -> bool:
    """Detect Apple Silicon (M1–M4)."""
    if platform.system() != "Darwin":
        return False
    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3
        )
        brand = result.stdout.strip().lower()
        return "apple" in brand
    except Exception:
        try:
            result = subprocess.run(
                ["uname", "-m"], capture_output=True, text=True, timeout=3
            )
            return "arm64" in result.stdout
        except Exception:
            return False


def _is_mlx_available() -> bool:
    """Check if MLX is installed."""
    try:
        import importlib
        return importlib.util.find_spec("mlx") is not None
    except Exception:
        return False


def _detect_windows_npu() -> bool:
    """Detect Copilot+ / AI PC NPU on Windows."""
    if platform.system() != "Windows":
        return False
    try:
        import winreg
        # Check for Qualcomm Snapdragon X Elite, Intel Core Ultra, or AMD Ryzen AI
        npu_indicators = [
            r"SYSTEM\CurrentControlSet\Enum\ACPI\QCOM0C01",  # Snapdragon X
            r"SYSTEM\CurrentControlSet\Enum\ACPI\INT345D",   # Intel AI boost
        ]
        for key_path in npu_indicators:
            try:
                winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                return True
            except Exception:
                continue

        # Check device description for NPU
        result = subprocess.run(
            ["wmic", "path", "win32_pnpentity", "get", "name"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.lower()
        return any(kw in output for kw in ["npu", "neural", "hexagon", "snapdragon x"])
    except Exception:
        return False


def _detect_gpu_type(vram_gb: float, gpu_name: str) -> tuple[HardwareTier, bool]:
    """
    Classify GPU tier and detect if CUDA/ROCm is available.
    Returns (tier, cuda_or_rocm_available).
    """
    gpu_lower = gpu_name.lower()

    if vram_gb <= 0.5:
        return HardwareTier.CPU_ONLY, False

    # Check for integrated graphics
    integrated_keywords = ["intel", "uhd", "iris", "radeon graphics", "vega", "navi 1"]
    is_integrated = any(kw in gpu_lower for kw in integrated_keywords) and vram_gb < 4.0
    if is_integrated:
        return HardwareTier.INTEGRATED_GPU, False

    # Check for dedicated GPU with CUDA
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            return HardwareTier.DEDICATED_GPU, True
    except Exception:
        pass

    # Check for ROCm (AMD)
    try:
        result = subprocess.run(
            ["rocm-smi", "--showid"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            return HardwareTier.DEDICATED_GPU, True
    except Exception:
        pass

    # Has significant VRAM but no detected driver — treat as dedicated
    if vram_gb >= 4.0:
        return HardwareTier.DEDICATED_GPU, False

    return HardwareTier.INTEGRATED_GPU, False


def _determine_quantization(
    hardware_tier: HardwareTier,
    vram_gb: float,
    ram_gb: float,
    model_vram_req: float = 8.0,
) -> QuantizationTier:
    """
    Choose quantization tier based on available memory.

    Rules:
    - INT8 is the DEFAULT standard (best accuracy/memory balance)
    - INT4 for budget/constrained hardware
    - INT3/INT2 only for extreme constraint
    - BF16/FP16 avoided unless explicitly configured
    """
    if hardware_tier == HardwareTier.CLOUD_ONLY:
        return QuantizationTier.INT8  # Irrelevant for cloud, but set a default

    effective_memory = vram_gb if vram_gb >= 2.0 else ram_gb

    # Comfortable headroom → INT8 (default)
    if effective_memory >= model_vram_req * 1.5:
        return QuantizationTier.INT8

    # Tight but workable → INT4
    if effective_memory >= model_vram_req * 0.75:
        return QuantizationTier.INT4

    # Severely constrained → INT3
    if effective_memory >= model_vram_req * 0.5:
        return QuantizationTier.INT3

    # Extreme compression only
    return QuantizationTier.INT2


def _build_ollama_options_for_profile(
    hardware_tier: HardwareTier,
    quantization: QuantizationTier,
    vram_gb: float,
    ram_gb: float,
) -> dict:
    """
    Build Ollama runtime options that enforce the quantization tier
    and memory efficiency settings.
    """
    options: dict = {
        "f16_kv": False,           # Use INT8 KV cache by default
        "num_keep": 24,            # Keep N tokens in KV cache across requests
    }

    # Map quantization to Ollama num_gpu_layers
    if hardware_tier == HardwareTier.DEDICATED_GPU:
        options["num_gpu"] = 99    # Offload all layers to GPU

    elif hardware_tier == HardwareTier.APPLE_SILICON:
        options["num_gpu"] = 1     # MLX handles this but set for Ollama fallback

    elif hardware_tier == HardwareTier.INTEGRATED_GPU:
        # Partial offload based on available VRAM
        if vram_gb >= 2.0:
            options["num_gpu"] = max(8, int(vram_gb * 4))
        else:
            options["num_gpu"] = 0

    else:  # CPU_ONLY
        options["num_gpu"] = 0
        # Use all CPU threads
        import os
        options["num_thread"] = os.cpu_count() or 4

    # KV cache precision based on quantization tier
    if quantization in (QuantizationTier.INT8, QuantizationTier.INT4):
        options["f16_kv"] = False  # Use quantized KV cache
    else:
        options["f16_kv"] = False  # Always false — no FP16 by default

    return options


def detect_inference_profile(
    vram_gb: float,
    ram_gb: float,
    gpu_name: str = "",
    model_vram_req: float = 8.0,
) -> InferenceProfile:
    """
    Main detection function — returns the complete inference profile for this system.
    """
    os_name = platform.system()
    notes = []

    # ── Apple Silicon ──────────────────────────────────────────────────────────
    if _is_apple_silicon():
        mlx_available = _is_mlx_available()
        hardware_tier = HardwareTier.APPLE_SILICON
        quantization = _determine_quantization(hardware_tier, vram_gb, ram_gb, model_vram_req)

        engine = InferenceEngine.MLX if mlx_available else InferenceEngine.OLLAMA
        if not mlx_available:
            notes.append(
                "MLX not installed — using Ollama. Install MLX for 2-3x faster inference: pip install mlx-lm"
            )
        else:
            notes.append(
                "MLX detected — using unified memory pool. No VRAM/RAM split needed."
            )

        return InferenceProfile(
            engine=engine,
            hardware_tier=hardware_tier,
            quantization=quantization,
            vram_gb=vram_gb,
            ram_gb=ram_gb,
            supports_speculative=mlx_available,
            supports_mlx=mlx_available,
            recommended_ollama_options=_build_ollama_options_for_profile(
                hardware_tier, quantization, vram_gb, ram_gb
            ),
            notes=notes,
        )

    # ── Windows NPU (Copilot+ / AI PC) ────────────────────────────────────────
    if os_name == "Windows" and _detect_windows_npu():
        hardware_tier = HardwareTier.WINDOWS_NPU
        quantization = QuantizationTier.INT8  # NPU optimized for INT8

        notes.append(
            "Copilot+ NPU detected. LiteRT-LM / ONNX Runtime / DirectML recommended. "
            "Ollama will work but won't use NPU — use LiteRT-LM for maximum NPU throughput."
        )
        notes.append(
            "For Intel NPU: use OpenVINO backend. For AMD Ryzen AI: use Ryzen AI engine. "
            "For Qualcomm Snapdragon X: use QNN/Hexagon backend."
        )

        gpu_tier, has_cuda = _detect_gpu_type(vram_gb, gpu_name)
        engine = InferenceEngine.OLLAMA if has_cuda or vram_gb >= 4.0 else InferenceEngine.LITERT_LM

        return InferenceProfile(
            engine=engine,
            hardware_tier=hardware_tier,
            quantization=quantization,
            vram_gb=vram_gb,
            ram_gb=ram_gb,
            supports_speculative=vram_gb >= 4.0,
            supports_mlx=False,
            recommended_ollama_options=_build_ollama_options_for_profile(
                hardware_tier, quantization, vram_gb, ram_gb
            ),
            notes=notes,
        )

    # ── Dedicated GPU (NVIDIA/AMD) ─────────────────────────────────────────────
    gpu_tier, has_cuda = _detect_gpu_type(vram_gb, gpu_name)

    if gpu_tier == HardwareTier.DEDICATED_GPU:
        quantization = _determine_quantization(gpu_tier, vram_gb, ram_gb, model_vram_req)
        notes.append(
            f"Dedicated GPU detected ({gpu_name}, {vram_gb}GB). "
            f"Ollama will auto-detect {'CUDA' if 'nvidia' in gpu_name.lower() else 'ROCm'} backend."
        )

        return InferenceProfile(
            engine=InferenceEngine.OLLAMA,
            hardware_tier=HardwareTier.DEDICATED_GPU,
            quantization=quantization,
            vram_gb=vram_gb,
            ram_gb=ram_gb,
            supports_speculative=vram_gb >= 8.0,
            supports_mlx=False,
            recommended_ollama_options=_build_ollama_options_for_profile(
                HardwareTier.DEDICATED_GPU, quantization, vram_gb, ram_gb
            ),
            notes=notes,
        )

    # ── Integrated GPU ─────────────────────────────────────────────────────────
    if gpu_tier == HardwareTier.INTEGRATED_GPU:
        quantization = _determine_quantization(gpu_tier, vram_gb, ram_gb, model_vram_req)
        notes.append(
            f"Integrated GPU detected. Partial GPU offload possible ({vram_gb}GB shared VRAM). "
            f"Use heavily quantized models (INT4/INT3) for acceptable performance."
        )

        return InferenceProfile(
            engine=InferenceEngine.OLLAMA,
            hardware_tier=HardwareTier.INTEGRATED_GPU,
            quantization=quantization,
            vram_gb=vram_gb,
            ram_gb=ram_gb,
            supports_speculative=False,
            supports_mlx=False,
            recommended_ollama_options=_build_ollama_options_for_profile(
                HardwareTier.INTEGRATED_GPU, quantization, vram_gb, ram_gb
            ),
            notes=notes,
        )

    # ── CPU Only / Legacy ──────────────────────────────────────────────────────
    if ram_gb >= 8.0:
        quantization = _determine_quantization(HardwareTier.CPU_ONLY, 0, ram_gb, model_vram_req)
        notes.append(
            "No dedicated GPU detected. Using CPU inference via llama.cpp/Ollama. "
            "Expect slower inference. Use smallest models (gemma3:4b INT4 or smaller)."
        )
        notes.append(
            f"AVX2/AVX-512 will be used if available on this CPU. "
            f"RAM available for inference: {ram_gb}GB."
        )

        return InferenceProfile(
            engine=InferenceEngine.LLAMA_CPP,
            hardware_tier=HardwareTier.CPU_ONLY,
            quantization=quantization,
            vram_gb=0.0,
            ram_gb=ram_gb,
            supports_speculative=False,
            supports_mlx=False,
            recommended_ollama_options=_build_ollama_options_for_profile(
                HardwareTier.CPU_ONLY, quantization, 0.0, ram_gb
            ),
            notes=notes,
        )

    # ── No viable local inference ──────────────────────────────────────────────
    notes.append(
        f"Insufficient RAM ({ram_gb}GB) for local inference. "
        f"All agents must use cloud models."
    )
    return InferenceProfile(
        engine=InferenceEngine.CLOUD_ONLY,
        hardware_tier=HardwareTier.CLOUD_ONLY,
        quantization=QuantizationTier.INT8,
        vram_gb=0.0,
        ram_gb=ram_gb,
        supports_speculative=False,
        supports_mlx=False,
        notes=notes,
    )


def get_quant_suffix(quantization: QuantizationTier) -> str:
    """Return the Ollama model tag suffix for a quantization tier."""
    return {
        QuantizationTier.INT8:  ":q8_0",
        QuantizationTier.INT4:  ":q4_k_m",
        QuantizationTier.INT3:  ":q3_k_m",
        QuantizationTier.INT2:  ":q2_k",
        QuantizationTier.FP16:  ":fp16",
        QuantizationTier.BF16:  "",  # default
    }.get(quantization, "")


def apply_quantization_to_model_id(model_id: str, quantization: QuantizationTier) -> str:
    """
    Append the quantization suffix to an Ollama model ID.
    e.g. ollama/gemma3:4b + INT4 → ollama/gemma3:4b-q4_k_m
    Only applies to Ollama models — cloud models are unaffected.
    """
    if not model_id.startswith("ollama/"):
        return model_id

    # Don't double-apply quantization
    if any(q in model_id for q in [":q8", ":q4", ":q3", ":q2", ":fp16"]):
        return model_id

    suffix = get_quant_suffix(quantization)
    if suffix:
        # Insert before any existing tag
        if ":" in model_id.split("/")[-1]:
            return model_id + suffix.replace(":", "-")
        return model_id + suffix

    return model_id
