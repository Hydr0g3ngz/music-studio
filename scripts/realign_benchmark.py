"""Compare alignment on identical ASR text, reusing one aligner across the suite."""

import argparse
import copy
import math
import time
from pathlib import Path

from ablate import link
from benchmark import GpuMonitor, freeze_engine, report_scores
from benchmark_lib import local_path, tokens, validate_suite

from music_studio.config import Settings
from music_studio.io import fingerprint, read_json, sha256, write_json
from music_studio.pipeline import run_worker


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/suite-v1.json"))
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/data"))
    parser.add_argument("--recognize", action="store_true")
    parser.add_argument(
        "--native-input",
        action="store_true",
        help="Use batch-cached pre-alignment ASR output; verify identical text",
    )
    parser.add_argument(
        "--qwen-native-windows",
        action="store_true",
        help="Restore 60s containers only if every chunk has one unchanged output",
    )
    parser.add_argument(
        "--guide-from",
        type=Path,
        help="Reuse verified Whisper small ASR outputs; never gold reference lyrics",
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("Choose a fresh output folder")
    manifest = read_json(args.manifest)
    validate_suite(manifest, args.data)
    overrides = read_json(args.settings)
    overrides = {k: v for k, v in overrides.items() if not k.startswith("_")}
    args.output.mkdir(parents=True)
    engine = freeze_engine(args.output)
    records, requests = {}, []
    started = time.perf_counter()
    for case in manifest["cases"]:
        source = local_path(args.baseline, case["id"])
        previous = read_json(source / "benchmark-run.json")
        if previous["status"] != "complete":
            raise ValueError(f"Incomplete baseline: {case['id']}")
        directory = local_path(args.output, case["id"])
        directory.mkdir()
        for record in previous["stages"].values():
            for relative, digest in record["artifacts"].items():
                origin = local_path(source, relative)
                if sha256(origin) != digest:
                    raise ValueError(f"Changed baseline artifact: {origin}")
                link(origin, local_path(directory, relative))
        for name in ("source", "vocals", "instrumental"):
            relative = f"audio/{name}.wav"
            if (source / relative).exists() and not (directory / relative).exists():
                link(source / relative, directory / relative)
        settings = Settings(**{**previous["settings"], **overrides}).resolved()
        if args.guide_from and not args.recognize:
            settings.device = "cpu"
        prediction = copy.deepcopy(read_json(source / "prediction.json"))
        run = copy.deepcopy(previous)
        run.update(
            status="complete",
            settings=settings.model_dump(),
            executed_stages=[],
            inherited_from=str(source.resolve()),
            inherited_prediction_sha256=sha256(source / "prediction.json"),
            attempts=[],
        )
        run["signature"] = fingerprint(
            {
                "settings": settings.model_dump(),
                "source_hash": previous["audio"]["source_hash"],
                "parent_prediction": sha256(source / "prediction.json"),
                "operation": "recognize" if args.recognize else "align",
            }
        )
        for value in run["stages"].values():
            value["inherited"] = True
        if "lyrics" in prediction:
            link(source / "analysis/lyrics.json", directory / "analysis/lyrics-input.json")
            if args.native_input or args.qwen_native_windows:
                from music_studio.backends.lyric_alignment import source_duration
                from music_studio.schema import Lyrics

                native_path = source / "analysis/lyrics-input.json"
                native = (
                    read_json(native_path)
                    if args.native_input
                    else copy.deepcopy(prediction["lyrics"])
                )
                language = settings.language or "en"

                def text_tokens(value, language=language):
                    return tokens(" ".join(s["text"] for s in value["segments"]), language)

                if text_tokens(native) != text_tokens(prediction["lyrics"]):
                    raise ValueError("Cached native ASR text differs from the measured prediction")
                if args.qwen_native_windows:
                    if (
                        previous["settings"].get("asr_backend") != "qwen"
                        or previous["settings"].get("lyrics_alignment") == "whisper"
                    ):
                        raise ValueError(
                            "Native-window restoration requires the original 60s Qwen recipe"
                        )
                    duration = (
                        math.ceil(
                            source_duration(directory / f"audio/{settings.lyrics_input}.wav")
                            * 16000
                        )
                        / 16000
                    )
                    chunks = math.ceil(duration / 60)
                    if len(native["segments"]) != chunks or [
                        s["id"] for s in native["segments"]
                    ] != [f"l{i:04d}" for i in range(chunks)]:
                        raise ValueError(
                            "Native windows unavailable: a chunk output is missing or split"
                        )
                    for i, line in enumerate(native["segments"]):
                        line.update(start=i * 60, end=min((i + 1) * 60, duration), words=[])
                    native["timing_method"] = (
                        "qwen_coarse_segments_restored_from_complete_chunk_sequence"
                    )
                Lyrics.model_validate(native)
                write_json(directory / "analysis/lyrics-input.json", native)
                run["native_input"] = {
                    "sha256": sha256(directory / "analysis/lyrics-input.json"),
                    "source": "batch_cached_native"
                    if args.native_input
                    else "complete_60s_chunk_sequence",
                    "text_unchanged": True,
                }
            if args.guide_from:
                guide_folder = local_path(args.guide_from, case["id"])
                guide_run = read_json(guide_folder / "benchmark-run.json")
                if (
                    guide_run["status"] != "complete"
                    or guide_run["settings"]["asr_model"] != "small"
                    or guide_run["settings"].get("asr_revision")
                    != "536b0662742c02347bc0e980a01041f333bce120"
                    or guide_run["settings"].get("lyrics_alignment", "native") != "native"
                    or guide_run["settings"].get("lyrics_input", "vocals") != "vocals"
                    or guide_run["settings"].get("asr_segmentation", "whole") != "whole"
                    or guide_run["settings"].get("seed", 0) != settings.seed
                    or guide_run["settings"].get("language") != settings.language
                ):
                    raise ValueError(
                        "Guide must be a matching, measured native Whisper small prediction"
                    )
                seeded_engine = args.guide_from / "_engine/music_studio/backends/lyrics.py"
                if (
                    not seeded_engine.exists()
                    or "ctranslate2.set_random_seed"
                    not in seeded_engine.read_text(encoding="utf-8")
                ):
                    raise ValueError("Guide must record an engine that seeds CTranslate2")
                vocal_hash = sha256(directory / "audio/vocals.wav")
                if vocal_hash != sha256(guide_folder / "audio/vocals.wav"):
                    raise ValueError("Acoustic guide uses different audio")
                guide_path = guide_folder / "analysis/lyrics.json"
                if sha256(guide_path) not in guide_run["stages"]["lyrics"]["artifacts"].values():
                    raise ValueError("Acoustic guide artifact changed")
                write_json(
                    directory / "analysis/anchor-guide.json",
                    {
                        "format": "whisper-small-guide-v1",
                        "audio_sha256": vocal_hash,
                        "language": settings.language,
                        "seed": settings.seed,
                        "model_revision": "536b0662742c02347bc0e980a01041f333bce120",
                        "lyrics": read_json(guide_path),
                        "provenance": {
                            "run": str(guide_folder.resolve()),
                            "prediction_sha256": sha256(guide_path),
                            "settings": guide_run["settings"],
                            "metrics": guide_run["stages"]["lyrics"]["metrics"],
                        },
                    },
                )
                run["signature"] = fingerprint(
                    {
                        "operation_signature": run["signature"],
                        "guide_prediction_sha256": sha256(guide_path),
                        "guide_audio_sha256": vocal_hash,
                    }
                )
            run.update(status="running", executed_stages=["lyrics" if args.recognize else "align"])
            requests.append(
                {
                    "stage": "lyrics" if args.recognize else "align",
                    "case_id": case["id"],
                    "settings": settings.model_dump(),
                    "output": str(directory.resolve()),
                    "result": str((directory / "analysis/lyrics.json").resolve()),
                    "align_input": settings.lyrics_input,
                }
            )
        records[case["id"]] = (directory, prediction, run)
    monitor = GpuMonitor()
    monitor.thread.start()
    try:
        batch = run_worker(
            {
                "stage": "lyrics_batch" if args.recognize else "align_batch",
                "settings": requests[0]["settings"],
                "output": str(args.output.resolve()),
                "requests": requests,
                "result": str((args.output / "batch.json").resolve()),
                "engine_path": str(engine),
            },
            args.output / "batch.log",
        )
    finally:
        monitor.stop.set()
        monitor.thread.join(timeout=4)
    statuses = {row["id"]: row for row in batch["cases"]}
    failures = []
    for case_id, (directory, prediction, run) in records.items():
        if case_id in statuses:
            status = statuses[case_id]
            run["status"] = status["status"]
            if status["status"] == "complete":
                result_path = directory / "analysis/lyrics.json"
                aligned = read_json(result_path)
                language = run["settings"].get("language") or "en"
                before = tokens(
                    " ".join(line["text"] for line in prediction["lyrics"]["segments"]), language
                )
                after = tokens(" ".join(line["text"] for line in aligned["segments"]), language)
                if not args.recognize and before != after:
                    raise ValueError(f"Alignment changed recognition text: {case_id}")
                prediction["lyrics"] = aligned
                run["stages"]["lyrics"] = {
                    "inherited": False,
                    "operation": "recognition_and_alignment"
                    if args.recognize
                    else "alignment_only",
                    "artifacts": {"analysis/lyrics.json": sha256(result_path)},
                    "metrics": {
                        **read_json(result_path.with_suffix(".metrics.json")),
                        "model_loading": "no model inference; verified cached guide, CPU matching"
                        if args.guide_from
                        else "shared models; warm after first case",
                        "recognition": "executed" if args.recognize else "inherited unchanged",
                    },
                }
            else:
                run["error"] = status["error"]
                failures.append(status)
        write_json(directory / "benchmark-run.json", run)
        if run["status"] == "complete":
            write_json(directory / "prediction.json", prediction)
    write_json(
        args.output / "session.json",
        {
            "protocol": "music-studio-lyrics-v3",
            "driver_sha256": sha256(Path(__file__)),
            "suite_sha256": sha256(args.manifest),
            "baseline": str(args.baseline.resolve()),
            "acoustic_guide_from": str(args.guide_from.resolve()) if args.guide_from else None,
            "native_input": "cached pre-alignment ASR"
            if args.native_input
            else "restored complete 60s Qwen chunk sequence"
            if args.qwen_native_windows
            else "measured parent prediction (may include prior alignment)",
            "overrides": overrides,
            "stages": ["lyrics" if args.recognize else "align"],
            "failures": failures,
            "engine_hashes": {str(p.relative_to(engine)): sha256(p) for p in engine.rglob("*.py")},
            "wall_seconds": round(time.perf_counter() - started, 3),
            "gpu": monitor.summary(),
            "timing_scope": "CPU matching only using verified cached ASR and acoustic guides; "
            "no neural inference or model loading. GPU samples may reflect other work. "
            "Session wall time includes cloning/hash checks and worker startup."
            if args.guide_from
            else "Shared models across cases. Case stage elapsed times exclude "
            "batch/process startup. Cold-process timings unavailable; do not compare with "
            "cold-process ASR or full-pipeline timings.",
        },
    )
    report = report_scores(manifest["cases"], args.data, args.output)
    print(report["summary"], flush=True)
    if failures or report["missing_cases"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
