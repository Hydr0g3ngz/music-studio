"""Probe CUDA in a disposable process; keep the desktop server off the GPU."""

import importlib.util
import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_dll_handles = []


def prepare_cuda_libraries():
    """Expose the bundled CUDA/cuDNN DLLs to CTranslate2, without a system toolkit."""
    if os.name != "nt":
        return
    spec = importlib.util.find_spec("torch")
    if spec is None or not spec.origin:
        return
    library = str(Path(spec.origin).parent / "lib")
    if library not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = library + os.pathsep + os.environ.get("PATH", "")
    if not _dll_handles and Path(library).is_dir():
        _dll_handles.append(os.add_dll_directory(library))


def probe_cuda():
    result = {"cuda_available": False, "name": None, "memory_mb": None,
              "torch": None, "cuda_runtime": None, "reason": ""}
    try:
        prepare_cuda_libraries()
        import torch

        result.update(torch=torch.__version__, cuda_runtime=torch.version.cuda)
        if not torch.version.cuda:
            result["reason"] = "cpu_runtime"
        elif not torch.cuda.is_available():
            result["reason"] = "driver_unavailable"
        else:
            # Allocation alone does not detect an unsupported GPU architecture.
            sample = torch.ones((32, 32), device="cuda")
            assert (sample @ sample).sum().item() == 32768
            torch.cuda.synchronize()
            import ctranslate2

            supported = ctranslate2.get_supported_compute_types("cuda")
            if "int8_float16" not in supported:
                raise RuntimeError("Whisper int8_float16 is unsupported on this GPU")
            properties = torch.cuda.get_device_properties(0)
            result.update(cuda_available=True, name=properties.name,
                          memory_mb=round(properties.total_memory / 1024**2))
    except Exception as error:
        result.update(reason="cuda_check_failed", detail=str(error)[:800])
    return result


@lru_cache(maxsize=1)
def acceleration_status():
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        environment = {**os.environ, "PYTHONUTF8": "1"}
        completed = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "music_studio.acceleration"],
            # A controller thread is already reading stdin. On Windows, inheriting
            # that pipe can block the child's Python startup before any code runs.
            stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
            creationflags=flags, env=environment, check=True,
        )
        return json.loads(completed.stdout.splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        return {"cuda_available": False, "name": None, "memory_mb": None,
                "reason": "cuda_check_failed", "detail": str(error)[:800]}


if __name__ == "__main__":
    print(json.dumps(probe_cuda(), ensure_ascii=False))
