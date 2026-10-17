"""Run with the bundled Python: offline inference, alignment and export checks."""

import argparse
import importlib.metadata
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

import music_studio
from music_studio.config import Settings
from music_studio.io import read_json, sha256, write_json
from music_studio.pipeline import analyze
from music_studio.validation import validate_project


def verify(payload, workspace, device="auto"):
    payload, workspace = payload.resolve(), workspace.resolve()
    assert Path(sys.executable).resolve().is_relative_to(payload)
    assert Path(music_studio.__file__).resolve().is_relative_to(payload)
    assert importlib.metadata.version("music-studio-local") == music_studio.__version__
    manifest = read_json(payload / "models/BUNDLED-MODELS.json")
    for item in manifest["files"]:
        path = (payload / item["file"]).resolve()
        assert path.is_relative_to(payload) and sha256(path) == item["sha256"]
    import torch

    from music_studio.acceleration import acceleration_status

    acceleration = acceleration_status()
    expected = "2.5.1+cu121" if manifest["profile"] == "cuda-small" else "2.5.1+cpu"
    assert torch.__version__ == expected
    device = ("cuda" if acceleration["cuda_available"] else "cpu") if device == "auto" else device
    if device == "cuda":
        assert acceleration["cuda_available"], acceleration
    workspace.mkdir(parents=True, exist_ok=True)
    source = Path(music_studio.__file__).parent / "ui/demo/audio/source.ogg"
    audio, rate = sf.read(source, dtype="float32", always_2d=True)
    # A vocal passage from the bundled credited CC BY 3.0 demo, not precomputed results.
    source = workspace / "input.wav"
    sf.write(source, audio[10 * rate:22 * rate], rate, subtype="FLOAT")
    started = time.monotonic()
    project = analyze(source, workspace / "analysis", Settings(
        device=device, offline=True, model_dir=str(payload / "models"), language="en",
    ).resolved())
    for name in ("source", "vocals", "instrumental"):
        output, output_rate = sf.read(workspace / "analysis" / project.assets[name],
                                     dtype="float32", always_2d=True)
        assert len(output) == 12 * rate and output_rate == rate
        assert np.isfinite(output).all()
    assert project.melody.notes and project.lyrics.segments
    validation = validate_project(workspace / "analysis/project.json")
    report = {"seconds": round(time.monotonic() - started, 3), "input_seconds": 12,
              "offline": True, "torch": torch.__version__, "version": music_studio.__version__,
              "device": device, "acceleration": acceleration,
              "lyric_lines": len(project.lyrics.segments), "notes": len(project.melody.notes),
              "validation": validation}
    write_json(workspace / "report.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()
    verify(args.payload, args.workspace, args.device)
