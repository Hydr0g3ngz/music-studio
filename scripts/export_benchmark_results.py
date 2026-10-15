"""Publish aggregate metrics/provenance only. Never copy audio or reference lyrics."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

from music_studio.io import read_json, write_json


def logical_path(value):
    if not value:
        return value
    path = Path(value)
    return f"{path.parent.name}/{path.name}"


def publish(runs: Path, destination: Path, name: str, filename: str, hardware: dict | None = None):
    report = copy.deepcopy(read_json(runs / name / "report.json"))
    if report["missing_cases"] or report.get("scoring_errors"):
        raise ValueError(f"Cannot publish incomplete results: {name}")
    for case in report["cases"]:
        performance = case["performance"]
        performance["inherited_from"] = logical_path(performance.get("inherited_from"))
        for metric in performance["stages"].values():
            if metric.get("reused_pitch_from"):
                metric["reused_pitch_from"] = logical_path(metric["reused_pitch_from"])
            if metric.get("runtime_python"):
                metric["runtime_python"] = (
                    "optional-lyrics-runtime"
                    if "lyrics-env" in metric["runtime_python"]
                    else "main-runtime"
                )
    session = read_json(runs / name / "session.json")
    if session.get("protocol") == "music-studio-lyrics-v3":
        session.setdefault(
            "training_membership",
            "Unverified; engineering regression only. "
            "Qwen/Heart training membership is not fully disclosed.",
        )
    for key in ("baseline", "lyrics_from", "pitch_from", "acoustic_guide_from"):
        if session.get(key):
            session[key] = Path(session[key]).name
    report["provenance"] = session
    report["hardware"] = (
        hardware
        or session.get("hardware")
        or {
            "note": "Hardware was not recorded; supply --hardware "
            "for verified measurement metadata."
        }
    )
    write_json(destination / filename, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path(".artifacts/benchmark/runs"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results"))
    parser.add_argument(
        "--hardware", type=Path, help="JSON describing the actual measured hardware"
    )
    parser.add_argument(
        "--lyrics-v3", action="store_true", help="Publish the completed lyric v3 matrix"
    )
    parser.add_argument(
        "--lyrics-v4", action="store_true", help="Publish the completed 17-recording MIR-1K runs"
    )
    args = parser.parse_args()
    lyric_runs = (
        ("lyrics-small-seeded-v3", "lyrics-v3-small.json"),
        ("lyrics-turbo-seeded-v3", "lyrics-v3-turbo.json"),
        ("lyrics-qwen-production-v3", "lyrics-v3-qwen-vocals.json"),
        ("lyrics-qwen-source-production-v3", "lyrics-v3-qwen-source.json"),
        ("lyrics-heart-production-v3", "lyrics-v3-heart.json"),
        ("lyrics-qwen-vocals-v3", "lyrics-v3-qwen-cold-recognition.json"),
        ("lyrics-qwen-source-v3", "lyrics-v3-qwen-source-recognition.json"),
        ("lyrics-heart-v3", "lyrics-v3-heart-recognition.json"),
        ("lyrics-qwen-final-v3", "lyrics-v3-qwen-forced-alignment.json"),
        ("lyrics-qwen-guided-v3", "lyrics-v3-qwen-whisper-alignment.json"),
        ("lyrics-qwen-anchors-v3", "lyrics-v3-global-anchors.json"),
        ("lyrics-qwen-window-anchors-v3", "lyrics-v3-window-anchors.json"),
        ("lyrics-qwen-aligned-refined-v3", "lyrics-v3-turbo-legacy-qwen-alignment.json"),
        ("lyrics-turbo-aligned-v3", "lyrics-v3-turbo-unseeded-diagnostic.json"),
    )
    older_runs = (
        ("baseline-seeded-v1", "baseline.json"),
        ("balanced-v2-final", "balanced.json"),
        ("text-v2-final", "text-priority.json"),
        ("lyrics-vocal-small-frozen", "rejected-vocal-chunks.json"),
        ("beat-this-diagnostic", "diagnostic-beat-this-small0.json"),
    )
    runs = (
        (
            ("mir-small-v4", "lyrics-v4-mir-small.json"),
            ("mir-qwen-dual-v4", "lyrics-v4-mir-qwen-dual.json"),
        )
        if args.lyrics_v4
        else lyric_runs
        if args.lyrics_v3
        else older_runs
    )
    for name, filename in runs:
        publish(
            args.runs,
            args.output,
            name,
            filename,
            read_json(args.hardware) if args.hardware else None,
        )
    print(f"Published aggregate reports to {args.output}")


if __name__ == "__main__":
    main()
