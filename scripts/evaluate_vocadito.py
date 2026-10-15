"""Frozen independent vocal-note test with both human note annotators reported separately."""

import argparse
import csv
import importlib.metadata
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate_melody_next import midi_roundtrip  # noqa: E402
from rosvot_adapter import RosvotModel  # noqa: E402

from music_studio.config import Settings  # noqa: E402
from music_studio.export import write_midi  # noqa: E402
from music_studio.io import read_json, sha256, write_json  # noqa: E402
from music_studio.schema import Lyrics, Rhythm  # noqa: E402


def freeze(data: Path, destination: Path):
    with (data / "vocadito_metadata.csv").open(encoding="utf-8", newline="") as file:
        metadata = list(csv.DictReader(file))
    cases = []
    for row in metadata:
        key = "vocadito_" + row["track_id"]
        files = {
            "audio": f"Audio/{key}.wav",
            "f0": f"Annotations/F0/{key}_f0.csv",
            "A1": f"Annotations/Notes/{key}_notesA1.csv",
            "A2": f"Annotations/Notes/{key}_notesA2.csv",
        }
        cases.append(
            {
                "id": key,
                "singer": row["singer_id"],
                "language": row["language"],
                "files": files,
                "sha256": {k: sha256(data / v) for k, v in files.items()},
            }
        )
    manifest = {
        "version": 1,
        "dataset": "vocadito",
        "record": "https://zenodo.org/records/5578807",
        "license": "CC-BY-4.0",
        "source_zip_md5": "dea40fd18f14d899643c4ba221b33a46",
        "source_zip_sha256": "e0d6b99d3f9c594afe5ae5c4d7bdacebe569e53b809e90b89d1c771c4f9990e3",
        "protocol": "All 40 clips, test only, no threshold tuning. Both note annotators separate. "
        "Note onset tolerance 50ms; pitch tolerance 50 cents; offset max(50ms,20% duration). "
        "Failed cases remain in macro F1 denominators as zero. Singing-only, not mixtures.",
        "cases": cases,
    }
    write_json(destination, manifest)


def score(data, case, melody, f0_times, f0):
    import mir_eval

    intervals = np.asarray([[n.start, n.end] for n in melody.notes]).reshape(-1, 2)
    pitches = np.asarray([440 * 2 ** ((n.pitch - 69) / 12) for n in melody.notes])
    result = {}
    for annotator in ("A1", "A2"):
        truth = np.atleast_2d(np.loadtxt(data / case["files"][annotator], delimiter=","))
        truth_intervals = np.column_stack([truth[:, 0], truth[:, 0] + truth[:, 2]])
        metrics = {}
        for key, offset in (("onset_pitch", None), ("onset_offset_pitch", 0.2)):
            precision, recall, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
                truth_intervals,
                truth[:, 1],
                intervals,
                pitches,
                onset_tolerance=0.05,
                pitch_tolerance=50,
                offset_ratio=offset,
                offset_min_tolerance=0.05,
            )
            metrics[key] = {"precision": precision, "recall": recall, "f1": f1}
        result[annotator] = metrics
    truth = np.loadtxt(data / case["files"]["f0"], delimiter=",")
    # The stable engine serializes unvoiced frequency frames as JSON null.
    estimate = np.nan_to_num(np.asarray(f0, dtype=float), nan=0.0)
    result["f0"] = dict(
        mir_eval.melody.evaluate(
            truth[:, 0],
            truth[:, 1],
            np.asarray(f0_times, dtype=float),
            estimate,
        )
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--suite", type=Path, default=ROOT / "benchmarks/vocadito-v1.json")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--backend", choices=["crepe", "rosvot"])
    parser.add_argument("--upstream", type=Path)
    parser.add_argument("--checkpoints", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.freeze:
        if args.suite.exists():
            parser.error("Manifest already exists; use a new version to change the test set")
        freeze(args.data, args.suite)
        return
    if not args.backend or not args.output:
        parser.error("--backend and --output are required for evaluation")
    if (args.output / "report.json").exists():
        parser.error("Use a fresh output directory to preserve prior experiments")
    args.output.mkdir(parents=True, exist_ok=True)
    engine = args.output / "engine"
    engine.mkdir(exist_ok=True)
    for source in (
        Path(__file__),
        ROOT / "scripts/rosvot_adapter.py",
        ROOT / "scripts/evaluate_melody_next.py",
    ):
        shutil.copyfile(source, engine / source.name)
    shutil.copytree(
        ROOT / "src/music_studio",
        engine / "music_studio",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "demo", "static"),
    )
    identity = {
        "backend": args.backend,
        "suite_sha256": sha256(args.suite),
        "engine_sha256": {str(p.relative_to(engine)): sha256(p) for p in engine.rglob("*.py")},
    }
    import torch

    if args.device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA is unavailable; select --device cpu")
    identity["device"] = args.device
    torch.set_num_threads(4)
    torch.manual_seed(0)
    np.random.seed(0)
    model = None
    loading = time.perf_counter()
    if args.backend == "rosvot":
        model = RosvotModel(args.upstream, args.checkpoints, args.device)
        identity["weights"] = {
            str(p.relative_to(args.checkpoints)): sha256(p)
            for p in args.checkpoints.rglob("*")
            if p.is_file()
        }
    identity["loading_seconds"] = time.perf_counter() - loading
    rows = []
    for case in read_json(args.suite)["cases"]:
        folder = args.output / case["id"]
        folder.mkdir(exist_ok=True)
        start = time.perf_counter()
        row = {"id": case["id"], "singer": case["singer"], "language": case["language"]}
        try:
            for key, relative in case["files"].items():
                if sha256(args.data / relative) != case["sha256"][key]:
                    raise ValueError("Frozen dataset hash differs: " + relative)
            if args.device == "cuda":
                torch.cuda.reset_peak_memory_stats()
            audio = args.data / case["files"]["audio"]
            if model is not None:
                melody = model.predict(audio, folder)
                f0 = np.load(folder / "activations.npz")["f0"]
                times = np.arange(len(f0)) * 128 / 24000
            else:
                from music_studio.backends.melody import extract_melody

                melody = extract_melody(audio, folder, Settings(device=args.device).model_dump())
                contour = read_json(folder / "analysis/pitch.json")
                times, f0 = contour["times"], contour["frequency_hz"]
            if args.device == "cuda":
                torch.cuda.synchronize()
                row["peak_cuda_allocated_mb"] = torch.cuda.max_memory_allocated() / 1024**2
            else:
                row["peak_cuda_allocated_mb"] = None
            row["inference_seconds"] = time.perf_counter() - start
            write_json(folder / "melody.json", melody.model_dump())
            write_midi(
                folder / "melody.mid",
                melody,
                Rhythm(backend="roundtrip-only", bpm=120, beats=[]),
                Lyrics(language=None, timing_method="not-used", segments=[]),
            )
            row.update(
                status="complete",
                metrics=score(args.data, case, melody, times, f0),
                midi_max_error_seconds=midi_roundtrip(folder / "melody.mid", melody),
                prediction_sha256=sha256(folder / "melody.json"),
            )
        except Exception as error:
            import traceback

            traceback.print_exc()
            row.update(status="failed", error=str(error))
        rows.append(row)
        write_json(folder / "score.json", row)
        print(case["id"], row["status"], row.get("metrics", {}).get("A1"), flush=True)
    macro = {}
    for annotator in ("A1", "A2"):
        macro[annotator] = {
            key: float(
                np.mean(
                    [
                        r.get("metrics", {}).get(annotator, {}).get(key, {}).get("f1", 0)
                        for r in rows
                    ]
                )
            )
            for key in ("onset_pitch", "onset_offset_pitch")
        }
    report = {
        "identity": identity,
        "cases": rows,
        "macro": macro,
        "selected": len(rows),
        "completed": sum(r["status"] == "complete" for r in rows),
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("torch", "librosa", "numpy", "mir-eval", "torchcrepe")
        },
    }
    write_json(args.output / "report.json", report)
    print(json.dumps({"macro": macro, "completed": report["completed"]}), flush=True)
    if report["completed"] != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
