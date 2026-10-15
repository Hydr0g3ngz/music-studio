"""Rerun selected components, preserving and hashing unchanged baseline predictions."""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import time
from pathlib import Path

from benchmark import GpuMonitor, freeze_engine, report_scores
from benchmark_lib import local_path, validate_suite

from music_studio.config import Settings
from music_studio.io import fingerprint, read_json, sha256, write_json
from music_studio.pipeline import run_worker

DOMAINS = {
    "align": {"real_full_mix", "isolated_singing"},
    "lyrics": {"real_full_mix", "isolated_singing"},
    "melody": {"isolated_singing"},
    "rhythm": {"acoustic_guitar_comp"},
    "harmony": {"acoustic_guitar_comp"},
    "separate": {"real_multitrack_mix"},
}


def link(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--stage", choices=DOMAINS, action="append", default=[])
    parser.add_argument(
        "--lyrics-from",
        type=Path,
        help="Inherit measured lyrics from another run with identical source/vocal audio",
    )
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/suite-v1.json"))
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/data"))
    parser.add_argument("--beat-folds", type=Path, help="Pinned official GuitarSet 8-fold split")
    parser.add_argument("--case", action="append")
    parser.add_argument(
        "--pitch-from",
        type=Path,
        help="Control decoder comparisons using identical verified pitch contours",
    )
    parser.add_argument("--training-overlap", help="Known training overlap: diagnostic only")
    args = parser.parse_args()
    if not args.stage and not args.lyrics_from:
        raise ValueError("Select --stage or --lyrics-from")
    if args.output.exists():
        raise ValueError("Choose a fresh output directory; ablations never overwrite predictions")
    if "rhythm" in args.stage and "harmony" not in args.stage:
        raise ValueError("Rhythm affects chord boundaries: include --stage harmony")
    manifest = read_json(args.manifest)
    validate_suite(manifest, args.data)
    overrides = read_json(args.settings)
    if overrides.get("_batch_recognition"):
        if args.case or args.stage != ["lyrics"]:
            raise ValueError("Batch lyric profiles require the full suite and --stage lyrics")
        from realign_benchmark import main as run_batch

        run_batch(
            [
                "--baseline",
                str(args.baseline),
                "--output",
                str(args.output),
                "--settings",
                str(args.settings),
                "--manifest",
                str(args.manifest),
                "--data",
                str(args.data),
                "--recognize",
            ]
        )
        return
    configured_inheritance = overrides.pop("_lyrics_from", None)
    reuse_identical = overrides.pop("_reuse_identical_lyrics", False)
    if configured_inheritance and not args.lyrics_from:
        args.lyrics_from = Path(configured_inheritance)
    cases = manifest["cases"]
    if args.case:
        unknown = set(args.case) - {c["id"] for c in cases}
        if unknown:
            raise ValueError(f"Unknown cases: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in args.case]
    folds = (
        dict(row.split() for row in args.beat_folds.read_text().splitlines())
        if args.beat_folds
        else {}
    )
    args.output.mkdir(parents=True)
    engine_path = freeze_engine(args.output)
    started = time.perf_counter()
    monitor = GpuMonitor()
    monitor.thread.start()
    failures = []
    try:
        for case in cases:
            source = local_path(args.baseline, case["id"])
            previous = read_json(source / "benchmark-run.json")
            if previous["status"] != "complete":
                raise ValueError(f"Baseline incomplete: {case['id']}")
            for stage in previous["stages"].values():
                for relative, digest in stage["artifacts"].items():
                    if sha256(local_path(source, relative)) != digest:
                        raise ValueError(f"Baseline artifact changed: {case['id']}/{relative}")
            lyric_source = None
            if args.lyrics_from and case["domain"] in DOMAINS["lyrics"]:
                lyric_source = local_path(args.lyrics_from, case["id"])
                lyric_run = read_json(lyric_source / "benchmark-run.json")
                if lyric_run["status"] != "complete":
                    raise ValueError("Inherited lyrics are incomplete")
                for name in ("source", "vocals"):
                    if sha256(source / f"audio/{name}.wav") != sha256(
                        lyric_source / f"audio/{name}.wav"
                    ):
                        raise ValueError("Cannot inherit lyric times from different audio")
                for relative, digest in lyric_run["stages"]["lyrics"]["artifacts"].items():
                    if sha256(local_path(lyric_source, relative)) != digest:
                        raise ValueError("Inherited lyric artifact changed")
                previous["stages"]["lyrics"] = lyric_run["stages"]["lyrics"]
            settings = Settings(**{**previous["settings"], **overrides}).resolved()
            if folds and case["dataset"] == "guitarset":
                settings.rhythm_checkpoint = "fold" + folds[case["source_id"] + "_mix"]
            directory = local_path(args.output, case["id"])
            stages = [s for s in args.stage if case["domain"] in DOMAINS[s]]
            if reuse_identical and lyric_source and "lyrics" in stages:
                earlier = read_json(lyric_source / "benchmark-run.json")["settings"]
                fields = (
                    "asr_backend",
                    "asr_model",
                    "asr_revision",
                    "asr_segmentation",
                    "language",
                    "lyrics_alignment",
                    "seed",
                )
                same_config = all(earlier.get(k) == settings.model_dump().get(k) for k in fields)
                old_input = earlier.get("lyrics_input", "vocals")
                if same_config and sha256(source / f"audio/{settings.lyrics_input}.wav") == sha256(
                    lyric_source / f"audio/{old_input}.wav"
                ):
                    stages.remove("lyrics")
            (directory / "audio").mkdir(parents=True)
            for name in ("source", "vocals", "instrumental"):
                path = source / f"audio/{name}.wav"
                if path.is_file() and not ("separate" in stages and name != "source"):
                    link(path, directory / f"audio/{name}.wav")
            for name, record in previous["stages"].items():
                if name not in stages:
                    for relative in record["artifacts"]:
                        target = local_path(directory, relative)
                        if not target.exists():
                            origin = lyric_source if name == "lyrics" and lyric_source else source
                            link(local_path(origin, relative), target)
            if (
                (source / "analysis/rhythm.json").exists()
                and "rhythm" not in stages
                and not (directory / "analysis/rhythm.json").exists()
            ):
                link(source / "analysis/rhythm.json", directory / "analysis/rhythm.json")
            prediction = copy.deepcopy(read_json(source / "prediction.json"))
            if lyric_source:
                prediction["lyrics"] = read_json(lyric_source / "prediction.json")["lyrics"]
            run = {
                "status": "running",
                "settings": settings.model_dump(),
                "audio": previous["audio"],
                "stages": copy.deepcopy(previous["stages"]),
                "inherited_from": str(source.resolve()),
                "inherited_prediction_sha256": sha256(source / "prediction.json"),
                "inherited_lyrics_from": str(lyric_source.resolve()) if lyric_source else None,
                "inherited_lyrics_prediction_sha256": sha256(lyric_source / "prediction.json")
                if lyric_source
                else None,
                "executed_stages": stages,
                "signature": fingerprint({"settings": settings.model_dump(), "stages": stages}),
                "attempts": [{"started_at": time.time(), "executed_stages": stages}],
            }
            for value in run["stages"].values():
                value["inherited"] = True
            print(case["id"], stages or "inherited", flush=True)
            try:
                for stage in stages:
                    key = "lyrics" if stage == "align" else stage
                    result_path = directory / f"analysis/{key}.json"
                    if stage == "align":
                        link(
                            source / "analysis/lyrics.json",
                            directory / "analysis/lyrics-input.json",
                        )
                    tick = time.perf_counter()
                    if stage == "melody" and args.pitch_from:
                        if settings.melody_decoder != "stable":
                            raise ValueError("Pitch reuse currently supports the stable decoder")
                        import numpy as np

                        from music_studio.backends.melody import stable_notes_from_contour
                        from music_studio.schema import Melody

                        origin = local_path(args.pitch_from, case["id"])
                        original_run = read_json(origin / "benchmark-run.json")
                        if original_run["status"] != "complete":
                            raise ValueError("Pitch source run is incomplete")
                        for key in ("pitch_backend", "pitch_threshold", "seed"):
                            if original_run["settings"].get(key) != settings.model_dump().get(key):
                                raise ValueError(f"Pitch inference setting differs: {key}")
                        pitch_path = origin / "analysis/pitch.json"
                        if sha256(origin / "audio/vocals.wav") != sha256(
                            directory / "audio/vocals.wav"
                        ):
                            raise ValueError("Pitch contour belongs to different vocal audio")
                        digest = (
                            original_run["stages"]["melody"]["artifacts"]["analysis\\pitch.json"]
                            if "analysis\\pitch.json"
                            in original_run["stages"]["melody"]["artifacts"]
                            else original_run["stages"]["melody"]["artifacts"][
                                "analysis/pitch.json"
                            ]
                        )
                        if sha256(pitch_path) != digest:
                            raise ValueError("Pitch contour changed")
                        contour = read_json(pitch_path)
                        notes = stable_notes_from_contour(
                            np.asarray(contour["times"]),
                            np.asarray(
                                [f if f is not None else np.nan for f in contour["frequency_hz"]]
                            ),
                            np.asarray(contour["periodicity"]),
                            previous["audio"]["duration"],
                        )
                        result = Melody(
                            backend=f"{settings.pitch_backend}/stable", notes=notes
                        ).model_dump()
                        link(pitch_path, directory / "analysis/pitch.json")
                        write_json(result_path, result)
                        write_json(
                            result_path.with_suffix(".metrics.json"),
                            {
                                "elapsed_seconds": round(time.perf_counter() - tick, 3),
                                "device": "cpu",
                                "scope": "Decoder only; fixed pitch inference inherited. "
                                "Not a full-stage speed measurement.",
                                "reused_pitch_from": str(origin.resolve()),
                                "pitch_sha256": digest,
                            },
                        )
                    else:
                        result = run_worker(
                            {
                                "stage": stage,
                                "settings": settings.model_dump(),
                                "output": str(directory.resolve()),
                                "result": str(result_path.resolve()),
                                "engine_path": str(engine_path),
                            },
                            directory / f"logs/{stage}.log",
                        )
                    if stage != "separate":
                        prediction[key] = result
                    artifacts = [result_path]
                    if stage == "separate":
                        artifacts.extend(
                            directory / f"audio/{s}.wav" for s in ("vocals", "instrumental")
                        )
                    if stage == "melody":
                        artifacts.append(directory / "analysis/pitch.json")
                    run["stages"][key] = {
                        "inherited": False,
                        "artifacts": {str(p.relative_to(directory)): sha256(p) for p in artifacts},
                        "metrics": {
                            **read_json(result_path.with_suffix(".metrics.json")),
                            "process_wall_seconds": round(time.perf_counter() - tick, 3),
                        },
                    }
                run["status"] = "complete"
                write_json(directory / "prediction.json", prediction)
            except Exception as error:
                run.update(status="failed", error=str(error))
                failures.append({"id": case["id"], "error": str(error)})
                print(f"FAILED: {error}", flush=True)
            run["attempts"][0]["status"] = run["status"]
            write_json(directory / "benchmark-run.json", run)
    finally:
        monitor.stop.set()
        monitor.thread.join(timeout=4)
        engine = engine_path / "music_studio"
        write_json(
            args.output / "session.json",
            {
                "protocol": "music-studio-component-v1",
                "suite_sha256": sha256(args.manifest),
                "baseline": str(args.baseline.resolve()),
                "lyrics_from": str(args.lyrics_from.resolve()) if args.lyrics_from else None,
                "pitch_from": str(args.pitch_from.resolve()) if args.pitch_from else None,
                "overrides": overrides,
                "stages": args.stage,
                "failures": failures,
                "engine_hashes": {
                    str(p.relative_to(engine)): sha256(p)
                    for p in engine.rglob("*.py")
                    if "ui" not in p.parts
                },
                "folds_sha256": sha256(args.beat_folds) if args.beat_folds else None,
                "training_overlap": args.training_overlap,
                "wall_seconds": round(time.perf_counter() - started, 3),
                "gpu": monitor.summary(),
            },
        )
    report = report_scores(cases, args.data, args.output)
    print(report["summary"])
    if report["missing_cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
