"""Cheap dependency checks before accepting work; never import models or download weights."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

from ..lyric_models import runtime_python

MODULES = ("torch", "faster_whisper", "qwen_asr", "transformers")
WHISPER_HELP = (
    "Whisper 运行环境未就绪。请运行 .\\scripts\\setup.ps1 -Mode full 安装后重启软件。"
)
QWEN_HELP = (
    "Qwen 运行环境未就绪。请运行 .\\scripts\\setup_lyrics.ps1 安装后重启软件，"
    "或切换为 Whisper。"
)
HEART_HELP = (
    "HeartTranscriptor 运行环境未就绪。请先安装歌词独立环境并重启软件，或切换为 Whisper。"
)
ALIGN_HELP = (
    "Qwen 对齐环境未就绪。请运行 .\\scripts\\setup_lyrics.ps1 -Models qwen,aligner "
    "安装后重启软件，或切换为声学锚点。"
)


def probe_modules(python: str | None = None) -> dict[str, bool]:
    if python is None:
        return {name: importlib.util.find_spec(name) is not None for name in MODULES}
    if not Path(python).is_file():
        return dict.fromkeys(MODULES, False)
    script = (
        "import importlib.util, json; "
        f"print(json.dumps({{n:importlib.util.find_spec(n) is not None for n in {MODULES!r}}}))"
    )
    try:
        result = subprocess.run(
            [python, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        found = json.loads(result.stdout)
        return {name: found.get(name) is True for name in MODULES}
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return dict.fromkeys(MODULES, False)


def runtime_capabilities(config: dict) -> dict:
    base = probe_modules()
    optional = probe_modules(config["lyrics_python"]) if config.get("lyrics_python") else base
    return {
        "whisper": {"available": base["torch"] and base["faster_whisper"]},
        "qwen": {
            "available": optional["torch"] and optional["transformers"] and optional["qwen_asr"]
        },
        "heart": {"available": optional["torch"] and optional["transformers"]},
    }


def runtime_error(config: dict, scope: str) -> str | None:
    backend = config.get("asr_backend", "whisper")
    alignment = config.get("lyrics_alignment", "native")
    help_text = QWEN_HELP if backend == "qwen" else HEART_HELP if backend == "heart" else (
        ALIGN_HELP if alignment == "qwen" else WHISPER_HELP
    )
    try:
        python = runtime_python(config)
    except RuntimeError:
        return help_text
    found = probe_modules(python)
    if not found["torch"]:
        return help_text
    if scope in ("full", "lyrics", "retry"):
        required = {
            "whisper": ("faster_whisper",),
            "qwen": ("qwen_asr", "transformers"),
            "heart": ("transformers",),
        }[backend]
        if not all(found[name] for name in required):
            return help_text
    if alignment == "qwen" and not (found["qwen_asr"] and found["transformers"]):
        return ALIGN_HELP
    if alignment in ("anchors", "whisper") and not found["faster_whisper"]:
        return WHISPER_HELP
    return None
