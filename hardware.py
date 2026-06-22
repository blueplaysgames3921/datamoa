"""
Hardware detection — detects GPU, RAM, CPU, storage
Used by Config Agent to recommend appropriate models
"""

import logging
import platform
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)


@dataclass
class HardwareInfo:
    gpu_name: str
    gpu_vram_gb: float
    ram_gb: float
    cpu_cores: int
    cpu_name: str
    storage_free_gb: float
    platform: str
    can_run_local: bool


def detect_hardware() -> HardwareInfo:
    """
    Detect system hardware specs.
    Attempts GPU detection via multiple backends gracefully.
    """
    gpu_name = "No GPU detected"
    gpu_vram_gb = 0.0

    # Try NVIDIA via GPUtil
    try:
        import GPUtil
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]
            gpu_name = gpu.name
            gpu_vram_gb = round(gpu.memoryTotal / 1024, 1)
    except Exception:
        pass

    # Try Apple Silicon via system_profiler
    if gpu_vram_gb == 0.0 and platform.system() == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5
            )
            if "Apple M" in result.stdout:
                # Apple Silicon uses unified memory
                ram = psutil.virtual_memory().total / (1024 ** 3)
                gpu_name = "Apple Silicon (Unified Memory)"
                gpu_vram_gb = round(ram * 0.75, 1)  # ~75% of RAM available as VRAM
        except Exception:
            pass

    # Try AMD via rocm-smi
    if gpu_vram_gb == 0.0:
        try:
            import subprocess
            result = subprocess.run(
                ["rocm-smi", "--showmeminfo", "vram"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.splitlines()
                for line in lines:
                    if "Total Memory" in line:
                        try:
                            raw_value = int(line.split()[-1])
                        except (ValueError, IndexError):
                            continue

                        # rocm-smi's reported unit varies by version/output
                        # format — e.g. "VRAM Total Memory (B): 17179869184"
                        # on modern versions (bytes), vs. plain MB on older
                        # ones. Blindly treating the value as MB (the old
                        # behavior) would massively overcount a 16GB GPU
                        # (17179869184 / 1024 ≈ 16.7 million "GB"), which
                        # would make can_run_local always true and could
                        # recommend models far too large for the hardware.
                        # Detect the unit from the line itself and convert
                        # accordingly.
                        line_lower = line.lower()
                        if "(b)" in line_lower or "bytes" in line_lower:
                            gpu_vram_gb = round(raw_value / (1024 ** 3), 1)
                        elif "(kb)" in line_lower:
                            gpu_vram_gb = round(raw_value / (1024 ** 2), 1)
                        elif "(gb)" in line_lower:
                            gpu_vram_gb = round(float(raw_value), 1)
                        else:
                            # Fall back to the historic assumption: MB
                            gpu_vram_gb = round(raw_value / 1024, 1)

                        gpu_name = "AMD GPU"
                        break
        except Exception:
            pass

    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    cpu_cores = psutil.cpu_count(logical=False) or 1

    try:
        import cpuinfo
        cpu_name = cpuinfo.get_cpu_info().get("brand_raw", "Unknown CPU")
    except Exception:
        cpu_name = platform.processor() or "Unknown CPU"

    try:
        storage_free_gb = round(psutil.disk_usage("/").free / (1024 ** 3), 1)
    except Exception:
        storage_free_gb = 0.0

    # Determine if local inference is viable
    can_run_local = gpu_vram_gb >= 4.0 or ram_gb >= 16.0

    return HardwareInfo(
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        ram_gb=ram_gb,
        cpu_cores=cpu_cores,
        cpu_name=cpu_name,
        storage_free_gb=storage_free_gb,
        platform=platform.system(),
        can_run_local=can_run_local,
    )
