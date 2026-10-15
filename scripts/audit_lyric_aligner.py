"""Compare official raw-text and adapter-token inputs; references never enter this audit."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from music_studio.audio import load_mono
from music_studio.backends.lyric_alignment import load_aligner, tokens
from music_studio.config import Settings
from music_studio.io import read_json, sha256, write_json
from music_studio.lyric_models import MODELS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs", type=Path, default=Path(".artifacts/benchmark/runs/lyrics-qwen-vocals-v3")
    )
    parser.add_argument("--model-dir", type=Path, default=Path(".cache/models"))
    parser.add_argument("--case", action="append")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".artifacts/aligner-audit-v4.json"))
    parser.add_argument(
        "--summary", type=Path, default=Path("benchmarks/results/lyrics-v4-aligner-audit.json")
    )
    args = parser.parse_args()
    config = (
        Settings(
            device=args.device,
            model_dir=str(args.model_dir),
            offline=args.offline,
            lyrics_alignment="qwen",
        )
        .resolved()
        .model_dump()
    )
    model = load_aligner(config)
    records = []
    for identifier in args.case or ["gts-01", "gts-07", "jamalt-en-01"]:
        folder = args.runs / identifier
        prediction = folder / "prediction.json"
        source = folder / "audio/vocals.wav"
        lyrics = read_json(prediction)["lyrics"]
        # These measured native predictions have one coarse container per 60-second chunk.
        chosen = [line for line in lyrics["segments"] if line["start"] < 60]
        if any(line["end"] > 60.05 for line in chosen):
            raise ValueError("Audit input must have complete native containers within 60 seconds")
        text = " ".join(line["text"] for line in chosen)
        audio = load_mono(source, 16000)[: 60 * 16000]
        language = "Chinese" if lyrics["language"] == "zh" else "English"
        for mode in ("official_raw", "adapter_tokens"):
            supplied = text if mode == "official_raw" else " ".join(x[0] for x in tokens(text))
            start = time.perf_counter()
            result = list(model.align(audio=(audio, 16000), text=supplied, language=language)[0])
            records.append(
                {
                    "case": identifier,
                    "mode": mode,
                    "duration": len(audio) / 16000,
                    "count": len(result),
                    "invalid": sum(
                        not np.isfinite(x.start_time + x.end_time) or x.end_time <= x.start_time
                        for x in result
                    ),
                    "token_match": [x.text.casefold() for x in result]
                    == [x[0].casefold() for x in tokens(text)],
                    "elapsed_seconds": round(time.perf_counter() - start, 3),
                    "input_vocal_sha256": sha256(source),
                    "input_prediction_sha256": sha256(prediction),
                    "items": [
                        {"text": x.text, "start": x.start_time, "end": x.end_time} for x in result
                    ],
                }
            )
            row = {k: v for k, v in records[-1].items() if k != "items"}
            print(json.dumps(row), flush=True)
            write_json(args.output, records)
    write_json(
        args.summary,
        {
            "scope": "Three fixed interface diagnostics, not an alignment accuracy benchmark",
            "model": MODELS["aligner"],
            "sample_rate": 16000,
            "max_audio_seconds": 60,
            "dtype": "bfloat16" if config["device"] == "cuda" else "float32",
            "attention": "sdpa",
            "driver_sha256": sha256(Path(__file__)),
            "cases": [{k: v for k, v in row.items() if k != "items"} for row in records],
        },
    )


if __name__ == "__main__":
    main()
