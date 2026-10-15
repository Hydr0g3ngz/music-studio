"""Audio-only note regression: cached CREPE baseline versus an optional note model.

No lyric or note annotations are provided to the recognizer. Results include every
selected case; a failed case contributes zero F1 and is explicitly reported.
"""

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_lib import load_reference, score_case  # noqa: E402

from music_studio.export import write_midi  # noqa: E402
from music_studio.io import read_json, sha256, write_json  # noqa: E402
from music_studio.schema import Lyrics, Melody, Note, Rhythm  # noqa: E402


def revision(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def basic_pitch_predict(source, duration, model, output):
    from basic_pitch.inference import predict

    activations, _, events = predict(source, model_or_model_path=model)
    np.savez_compressed(output / "activations.npz", **activations)
    notes = []
    for start, end, pitch, amplitude, _ in events:
        start, end = max(0, float(start)), min(duration, float(end))
        if end <= start:
            continue
        notes.append(
            Note(
                id=f"n{len(notes):05d}",
                start=start,
                end=end,
                pitch=int(pitch),
                score=float(np.clip(amplitude, 0, 1)),
                velocity=int(np.clip(round(float(amplitude) * 127), 1, 127)),
            )
        )
    return Melody(
        backend="basic-pitch/onnx/upstream-defaults",
        notes=notes,
        warnings=["Raw polyphonic note estimates; activation scores are not calibrated accuracy."],
    )


def midi_roundtrip(path, melody):
    import mido

    active, notes, now = {}, [], 0.0
    for message in mido.MidiFile(path, charset="utf-8"):
        now += message.time
        if message.type == "note_on" and message.velocity:
            if message.note in active:
                raise ValueError("Overlapping notes share a MIDI pitch")
            active[message.note] = now
        elif message.type == "note_off" or message.type == "note_on" and not message.velocity:
            notes.append((active.pop(message.note), now, message.note))
    wanted = sorted((n.start, n.end, n.pitch) for n in melody.notes)
    if active or len(wanted) != len(notes):
        raise ValueError("Unterminated or missing MIDI notes")
    error = 0.0
    for actual, expected in zip(sorted(notes), wanted, strict=True):
        if actual[2] != expected[2]:
            raise ValueError("MIDI pitch differs from predicted note")
        error = max(error, abs(actual[0] - expected[0]), abs(actual[1] - expected[1]))
    if error > 0.01:
        raise ValueError("MIDI timing differs by more than 10ms")
    return error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=ROOT / "benchmarks/suite-v1.json")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--backend", choices=["cached", "basic-pitch", "rosvot"], required=True)
    parser.add_argument("--checkpoints", type=Path)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = read_json(args.suite)
    cases = [case for case in manifest["cases"] if "notes" in case.get("tasks", [])]
    if not cases:
        parser.error("Suite does not contain any note cases")
    if args.backend == "cached" and args.baseline is None:
        parser.error("--baseline is required for cached predictions")
    if (args.output / "report.json").exists():
        parser.error("Use a fresh output directory to preserve prior experiments")
    args.output.mkdir(parents=True, exist_ok=True)
    engine = args.output / "engine"
    engine.mkdir(exist_ok=True)
    for source in (
        Path(__file__),
        ROOT / "scripts/benchmark_lib.py",
        ROOT / "scripts/rosvot_adapter.py",
    ):
        shutil.copyfile(source, engine / source.name)
    script_digest = sha256(Path(__file__))
    identity = {"backend": args.backend, "suite_sha256": sha256(args.suite)}
    if args.backend == "rosvot":
        from rosvot_adapter import RosvotModel

        if args.upstream is None or args.checkpoints is None:
            parser.error("--upstream and --checkpoints are required for ROSVOT")
        model_start = time.perf_counter()
        model = RosvotModel(args.upstream, args.checkpoints, args.device)
        identity.update(
            source_revision=revision(args.upstream),
            device=args.device,
            adapter_sha256=sha256(ROOT / "scripts/rosvot_adapter.py"),
            model_loading_seconds=time.perf_counter() - model_start,
            checkpoints={
                str(p.relative_to(args.checkpoints)): sha256(p)
                for p in args.checkpoints.rglob("*")
                if p.is_file()
            },
        )
    if args.backend == "basic-pitch":
        if args.upstream is None:
            parser.error("--upstream is required for the optional Basic Pitch checkout")
        sys.path.insert(0, str(args.upstream.resolve()))
        from basic_pitch.inference import Model

        model_path = args.upstream / "basic_pitch/saved_models/icassp_2022/nmp.onnx"
        model_start = time.perf_counter()
        model = Model(model_path)
        identity.update(
            source_revision=revision(args.upstream),
            model_sha256=sha256(model_path),
            model_loading_seconds=time.perf_counter() - model_start,
        )
    rows = []
    for case in cases:
        output = args.output / case["id"]
        output.mkdir(exist_ok=True)
        reference = load_reference(case, args.data)
        start = time.perf_counter()
        try:
            if args.backend == "cached":
                path = args.baseline / case["id"] / "analysis/melody.json"
                melody = Melody.model_validate(read_json(path))
            elif args.backend == "basic-pitch":
                melody = basic_pitch_predict(
                    args.data / case["audio"], reference["duration"], model, output
                )
            else:
                melody = model.predict(args.data / case["audio"], output)
            write_json(output / "melody.json", melody.model_dump())
            write_midi(
                output / "melody.mid",
                melody,
                Rhythm(backend="constant-for-roundtrip", bpm=120, beats=[]),
                Lyrics(language=None, timing_method="not-used", segments=[]),
            )
            metrics = score_case(case, reference, {"melody": melody.model_dump()}, output)
            row = {
                "id": case["id"],
                "language": case["language"],
                "status": "complete",
                "metrics": metrics,
                "elapsed_seconds": time.perf_counter() - start,
                "midi_max_error_seconds": midi_roundtrip(output / "melody.mid", melody),
                "source_sha256": sha256(args.data / case["audio"]),
                "prediction_sha256": sha256(output / "melody.json"),
            }
        except Exception as error:
            row = {
                "id": case["id"],
                "language": case["language"],
                "status": "failed",
                "error": str(error),
                "elapsed_seconds": time.perf_counter() - start,
            }
        rows.append(row)
        write_json(output / "score.json", row)
        print(case["id"], row["status"], row.get("metrics", {}).get("note_onset_pitch"), flush=True)
    packages = {}
    for name in ("numpy", "onnxruntime", "librosa", "mir-eval", "torch", "pretty-midi"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    groups = {}
    for language in sorted({case["language"] for case in cases}):
        selected = [row for row in rows if row["language"] == language]
        groups[language] = {
            "cases": len(selected),
            "failures": sum(row["status"] != "complete" for row in selected),
            **{
                key: float(
                    np.mean([row.get("metrics", {}).get(key, {}).get("f1", 0) for row in selected])
                )
                for key in ("note_onset_pitch", "note_onset_offset_pitch")
            },
        }
    report = {
        "identity": identity,
        "packages": packages,
        "groups": groups,
        "cases": rows,
        "selected_cases": len(cases),
        "completed_cases": sum(r["status"] == "complete" for r in rows),
        "scope": "Frozen engineering regression; no reference lyrics or note times enter models. "
        "GTSinger is already used in development. "
        "Cached baseline has no inference timing comparison.",
        "script_sha256": script_digest,
    }
    write_json(args.output / "report.json", report)
    print(json.dumps(groups, indent=2), flush=True)
    if report["completed_cases"] != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
