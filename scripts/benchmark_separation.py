"""Compare local separators on the frozen suite's two public MUSDB7 previews."""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from benchmark_lib import multitrack_reference, si_sdr

from music_studio.io import read_json, sha256, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument(
        "--model", choices=("demucs-htdemucs", "mel-band-roformer-kj"), required=True
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a new output directory to retain previous evidence")
    args.output.mkdir(parents=True)
    suite = read_json(Path(__file__).resolve().parents[1] / "benchmarks/suite-v1.json")
    assets = [a for a in suite["assets"] if a["path"].startswith("musdb7/")]
    rows = []
    for index, asset in enumerate(assets):
        source = args.data / asset["path"]
        if sha256(source) != asset["sha256"]:
            raise ValueError("Frozen dataset hash changed: " + asset["path"])
        reference = multitrack_reference(source)
        folder = args.output / f"case-{index + 1}"
        folder.mkdir()
        source_wav = folder / "input.wav"
        sf.write(source_wav, reference["mixture"], 44100, subtype="FLOAT")
        output = folder / "output"
        request = {
            "input": str(source_wav.resolve()),
            "input_sha256": sha256(source_wav),
            "output": str(output.resolve()),
            "owner_pid": os.getpid(),
            "stage": "separate",
            "model": args.model,
            "settings": {
                "model_dir": str(args.model_dir.resolve()),
                "device": args.device,
                "seed": 0,
                "threads": 8,
                "separation_model": "htdemucs",
                "segment_seconds": 6,
                "mixture_consistency": True,
            },
        }
        request_path = folder / "request.json"
        write_json(request_path, request)
        environment = os.environ.copy()
        environment.update(TORCH_HOME=str(args.model_dir.resolve() / "torch"), HF_HUB_OFFLINE="1")
        started = time.perf_counter()
        with (folder / "worker.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(
                [
                    str(args.python.resolve()),
                    "-m",
                    "music_studio.studio.task_worker",
                    str(request_path.resolve()),
                ],
                env=environment,
                stdout=log,
                stderr=log,
            )
        row = {
            "case": asset["path"],
            "input_sha256": asset["sha256"],
            "exit_code": process.returncode,
            "wall_seconds": time.perf_counter() - started,
        }
        if process.returncode == 0:
            row.update(read_json(output / "result.json"))
            row["si_sdr_db"] = {}
            signals = {}
            for role in ("vocals", "instrumental"):
                audio, rate = sf.read(output / f"audio/{role}.wav", always_2d=True)
                assert audio.shape == reference[role].shape and rate == 44100
                assert np.isfinite(audio).all()
                signals[role] = audio
                row["si_sdr_db"][role] = si_sdr(reference[role], audio)
            row["mixture_max_error"] = float(
                np.max(np.abs(signals["vocals"] + signals["instrumental"] - reference["mixture"]))
            )
        rows.append(row)
        write_json(
            args.output / "results.json",
            {
                "model": args.model,
                "device": args.device,
                "scope": "Two frozen 7 s previews, not full MUSDB scores; no general SOTA claim",
                "rows": rows,
            },
        )
        print(json.dumps(row, ensure_ascii=True), flush=True)
    if any(r["exit_code"] for r in rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
