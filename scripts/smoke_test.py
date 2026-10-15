"""Run REAL models on an audio file. No fabricated lyrics, stems or notes.

Example: python scripts/smoke_test.py song.mp3 --device cuda --model-dir .cache/models
Uses a separate output folder and checks the exported song's actual timebase.
"""

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from music_studio.config import Settings
from music_studio.pipeline import analyze
from music_studio.validation import validate_project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".artifacts/smoke"))
    parser.add_argument("--model-dir", type=Path, default=Path(".cache/models"))
    parser.add_argument("--asr-model", default="small")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--language")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--sample-gpu", action="store_true")
    args = parser.parse_args()
    settings = Settings(
        device=args.device,
        model_dir=str(args.model_dir),
        asr_model=args.asr_model,
        language=args.language,
        offline=args.offline,
    )
    samples = []
    stop = threading.Event()

    def sample_gpu():
        while not stop.is_set():
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--id=0",
                        "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                samples.append(int(result.stdout.strip()))
            except (OSError, ValueError, subprocess.SubprocessError):
                return
            stop.wait(1)

    monitor = threading.Thread(target=sample_gpu, daemon=True)
    if args.sample_gpu:
        monitor.start()
    start = time.perf_counter()
    try:
        analyze(args.input, args.output, settings, resume=(args.output / "run.json").exists())
    finally:
        stop.set()
        if args.sample_gpu:
            monitor.join(timeout=6)
    report = validate_project(args.output)
    report["wall_seconds"] = round(time.perf_counter() - start, 2)
    if samples:
        report["gpu_baseline_mb"] = samples[0]
        report["gpu_sampled_peak_mb"] = max(samples)
        report["gpu_samples"] = len(samples)
        report["gpu_note"] = (
            "Whole-device memory sampled ~once/second; includes other applications."
        )
    (args.output / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
