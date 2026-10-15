"""Download, validate and score an upstream-annotated local regression suite.

Run from a source checkout; neural inference remains optional until the run command.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import shutil
import subprocess
import threading
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from benchmark_lib import load_reference, local_path, score_case, validate_suite

from music_studio.audio import decode_audio
from music_studio.config import Settings
from music_studio.io import fingerprint, read_json, sha256, write_json
from music_studio.pipeline import installed_versions, run_worker

ROOT = Path(__file__).resolve().parents[1]


def prepare(manifest: dict, root: Path):
    root.mkdir(parents=True, exist_ok=True)
    missing = []
    for item in manifest["assets"]:
        path = local_path(root, item["path"])
        if path.is_file() and path.stat().st_size == item["bytes"]:
            if sha256(path) == item["sha256"]:
                continue
        missing.append(item)

    def store(item, data):
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Downloaded file failed integrity check: {item['path']}")
        path = local_path(root, item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".part")
        temporary.write_bytes(data)
        temporary.replace(path)
        print(f"Downloaded {item['path']} ({len(data):,} bytes)", flush=True)

    def direct(item):
        for attempt in range(3):
            try:
                request = Request(item["url"], headers={"User-Agent": "MusicStudio-benchmark/0.1"})
                with urlopen(request, timeout=45) as response:
                    data = response.read(item["bytes"] + 1)
                store(item, data)
                return
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    direct_files = [item for item in missing if "archive_member" not in item]
    derived = [item for item in direct_files if "derived_from" in item]
    zip_downloads = [item for item in direct_files if item.get("archive_format") == "zip-download"]
    direct_files = [item for item in direct_files if item not in derived + zip_downloads]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(direct, direct_files))
    for item in zip_downloads:
        limit = item["bytes"] + 1024**2
        with urlopen(item["url"], timeout=60) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Mirrored audio archive exceeds the expected download size")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [
                n for n in archive.namelist() if Path(n).name == item["archive_member_basename"]
            ]
            if len(members) != 1:
                raise ValueError("Unexpected mirrored audio archive")
            info = archive.getinfo(members[0])
            if info.file_size != item["bytes"]:
                raise ValueError("Mirrored audio member size changed")
            with archive.open(info) as member:
                store(item, member.read(item["bytes"] + 1))
    for item in derived:
        import soundfile as sf

        if item["transform"] != "stereo-channel-mean-float32-wav-v1":
            raise ValueError("Unknown benchmark audio transform")
        audio, rate = sf.read(
            local_path(root, item["derived_from"]), dtype="float32", always_2d=True
        )
        buffer = io.BytesIO()
        sf.write(buffer, np.mean(audio, axis=1), rate, format="WAV", subtype="FLOAT")
        store(item, buffer.getvalue())
    archives = defaultdict(list)
    for item in missing:
        if "archive_member" in item:
            archives[item["url"]].append(item)
    if archives:
        from remotezip import RemoteZip

        for url, items in archives.items():
            for item in items:
                for attempt in range(3):
                    try:
                        with RemoteZip(url, timeout=45) as archive:
                            info = archive.getinfo(item["archive_member"])
                            if info.file_size != item["bytes"]:
                                raise ValueError(f"Archive member size changed: {item['path']}")
                            # Read one chosen member; never extract a remote directory tree.
                            store(item, archive.read(info))
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(attempt + 1)
    print(f"Ready: {len(manifest['assets'])} files, {len(manifest['cases'])} cases")


def selected_cases(manifest: dict, args) -> list[dict]:
    cases = manifest["cases"]
    if args.smoke:
        cases = [case for case in cases if case["smoke"]]
    if args.case:
        identifiers = set(args.case)
        unknown = identifiers - {case["id"] for case in manifest["cases"]}
        if unknown:
            raise ValueError(f"Unknown case IDs: {sorted(unknown)}")
        cases = [case for case in cases if case["id"] in identifiers]
    if not cases:
        raise ValueError("The selection contains no cases")
    return cases


def freeze_engine(output: Path) -> Path:
    destination = output / "_engine"
    source = Path(__import__("music_studio").__file__).parent
    if not destination.exists():
        shutil.copytree(
            source,
            destination / "music_studio",
            ignore=shutil.ignore_patterns("__pycache__", "ui", "*.pyc"),
        )
    return destination.resolve()


def run_case(case: dict, root: Path, output: Path, settings: Settings, engine_path=None) -> dict:
    config = settings.model_copy(update={"language": case["language"]}).resolved()
    source = local_path(root, case["audio"])
    directory = local_path(output, case["id"])
    engine_root = (
        engine_path / "music_studio"
        if engine_path
        else Path(__import__("music_studio").__file__).parent
    )
    files = [engine_root / n for n in ("audio.py", "worker.py", "config.py", "schema.py")]
    files += sorted((engine_root / "backends").glob("*.py"))
    signature = fingerprint(
        {
            "source": sha256(source),
            "settings": config.model_dump(),
            "domain": case["domain"],
            "code": {str(p.relative_to(engine_root)): sha256(p) for p in files},
            "packages": installed_versions(
                [
                    "torch",
                    "torchaudio",
                    "demucs",
                    "faster-whisper",
                    "ctranslate2",
                    "torchcrepe",
                    "librosa",
                ]
            ),
        }
    )
    run_path = directory / "benchmark-run.json"
    run = read_json(run_path) if run_path.exists() else {}
    if run and run.get("signature") != signature:
        raise ValueError("Settings/input/backend changed; choose a new --output directory")
    directory.mkdir(parents=True, exist_ok=True)
    run.update(signature=signature, settings=config.model_dump(), status="running")
    run.pop("error", None)
    attempt = {"started_at": time.time(), "status": "running", "executed_stages": []}
    run.setdefault("attempts", []).append(attempt)
    run.setdefault("stages", {})
    write_json(run_path, run)
    started = time.perf_counter()
    master = directory / "audio/source.wav"
    # A failed/interrupted stage is not reusable. Verify every cached audio dependency.
    audio = run.get("audio", {})
    if not master.is_file() or audio.get("source_hash") != sha256(master):
        info = decode_audio(source, master, sha256(source))
        run["audio"] = {"source_hash": sha256(master), "duration": info.duration}
        run["stages"] = {}
        write_json(run_path, run)

    def stage(name):
        result_path = directory / "analysis" / f"{name}.json"
        cached = run["stages"].get(name, {})
        artifacts = cached.get("artifacts", {})
        if name in ("lyrics", "melody"):
            inputs = [directory / "audio/vocals.wav"]
        elif name == "harmony":
            inputs = [directory / "audio/instrumental.wav", directory / "analysis/rhythm.json"]
        else:
            inputs = [master]
        dependency_hash = fingerprint({str(p.relative_to(directory)): sha256(p) for p in inputs})
        if (
            artifacts
            and cached.get("inputs") == dependency_hash
            and all(
                (directory / relative).is_file() and sha256(directory / relative) == digest
                for relative, digest in artifacts.items()
            )
        ):
            print(f"  reuse {name}", flush=True)
            return read_json(result_path)
        print(f"  {name}", flush=True)
        stage_start = time.perf_counter()
        result = run_worker(
            {
                "stage": name,
                "settings": config.model_dump(),
                "output": str(directory.resolve()),
                "result": str(result_path.resolve()),
                "engine_path": str(engine_path) if engine_path else None,
            },
            directory / "logs" / f"{name}.log",
        )
        paths = [result_path]
        if name == "separate":
            paths.extend(directory / f"audio/{kind}.wav" for kind in ("vocals", "instrumental"))
        if name == "melody":
            paths.append(directory / "analysis/pitch.json")
        run["stages"][name] = {
            "inputs": dependency_hash,
            "artifacts": {str(path.relative_to(directory)): sha256(path) for path in paths},
            "metrics": read_json(result_path.with_suffix(".metrics.json")),
        }
        run["stages"][name]["metrics"]["process_wall_seconds"] = round(
            time.perf_counter() - stage_start, 3
        )
        attempt["executed_stages"].append(name)
        write_json(run_path, run)
        return result

    try:
        prediction = {}
        if case["domain"] in ("real_full_mix", "lyrics_mandarin_karaoke_mix"):
            stage("separate")
            prediction["lyrics"] = stage("lyrics")
        elif case["domain"] == "real_multitrack_mix":
            stage("separate")
            prediction["separation"] = {
                "vocals": "audio/vocals.wav",
                "instrumental": "audio/instrumental.wav",
            }
        elif case["domain"] == "isolated_singing":
            shutil.copyfile(master, directory / "audio/vocals.wav")
            prediction["lyrics"] = stage("lyrics")
            prediction["melody"] = stage("melody")
        else:
            shutil.copyfile(master, directory / "audio/instrumental.wav")
            prediction["rhythm"] = stage("rhythm")
            prediction["harmony"] = stage("harmony")
        run.update(status="complete", wall_seconds=round(time.perf_counter() - started, 3))
        write_json(directory / "prediction.json", prediction)
        return prediction
    except KeyboardInterrupt:
        run["status"] = "interrupted"
        raise
    except Exception as error:
        run.update(status="failed", error=str(error))
        raise
    finally:
        attempt.update(status=run["status"], wall_seconds=round(time.perf_counter() - started, 3))
        if "error" in run:
            attempt["error"] = run["error"]
        write_json(run_path, run)


def report_scores(cases: list[dict], root: Path, output: Path) -> dict:
    scored, missing, scoring_errors = [], [], []
    for case in cases:
        path = output / case["id"] / "prediction.json"
        run_path = path.parent / "benchmark-run.json"
        if (
            not path.exists()
            or not run_path.exists()
            or read_json(run_path)["status"] != "complete"
        ):
            missing.append(case["id"])
            continue
        try:
            metrics = score_case(case, load_reference(case, root), read_json(path), path.parent)
        except Exception as error:
            missing.append(case["id"])
            scoring_errors.append({"id": case["id"], "error": str(error)})
            continue
        run = read_json(run_path)
        executed = run.get(
            "executed_stages", (run.get("attempts") or [{}])[-1].get("executed_stages", [])
        )
        result = {
            "id": case["id"],
            "dataset": case["dataset"],
            "language": case["language"],
            "domain": case["domain"],
            "split": case.get("split", "regression"),
            "metrics": metrics,
            "performance": {
                "audio_seconds": run["audio"]["duration"],
                "executed_stages": executed,
                "inherited_from": run.get("inherited_from"),
                "stages": {
                    name: {
                        **value["metrics"],
                        "inherited": value.get("inherited", False),
                        "process_rtf": value["metrics"]["process_wall_seconds"]
                        / run["audio"]["duration"]
                        if value["metrics"].get("process_wall_seconds") is not None
                        else None,
                    }
                    for name, value in run["stages"].items()
                },
                "attempts": run.get("attempts", []),
            },
        }
        scored.append(result)
        write_json(path.parent / "scores.json", result)
    grouped = {}
    for dataset in sorted({case["dataset"] for case in scored}):
        languages = sorted(
            {case["language"] or "instrumental" for case in scored if case["dataset"] == dataset}
        )
        for language in languages:
            rows = [
                r
                for r in scored
                if r["dataset"] == dataset and (r["language"] or "instrumental") == language
            ]
            summary = {"cases": len(rows)}
            lyrics = [row["metrics"]["lyrics"] for row in rows if "lyrics" in row["metrics"]]
            if lyrics:
                total = sum(row["reference_tokens"] for row in lyrics)
                summary["micro_error_rate"] = sum(row["errors"] for row in lyrics) / total
                summary["reference_tokens"] = total
            for name, key in (
                ("note_onset_pitch", "f1"),
                ("note_onset_offset_pitch", "f1"),
                ("beats", "F-measure"),
                ("chords", "majmin"),
            ):
                values = [row["metrics"][name][key] for row in rows if name in row["metrics"]]
                if values:
                    summary[f"macro_{name}_{key}"] = float(np.mean(values))
            for stem in ("vocals", "instrumental"):
                for metric in ("si_sdr_db", "si_sdri_db"):
                    values = [
                        row["metrics"]["separation"][stem][metric]
                        for row in rows
                        if "separation" in row["metrics"]
                        and row["metrics"]["separation"][stem][metric] is not None
                    ]
                    if values:
                        summary[f"macro_{stem}_{metric}"] = float(np.mean(values))
            grouped[f"{dataset}/{language}"] = summary
    runtime = {}
    for name in ("separate", "lyrics", "melody", "rhythm", "harmony"):
        rows = [r for r in scored if name in r["performance"]["executed_stages"]]
        if rows:
            if any(
                r["performance"]["stages"][name].get("process_wall_seconds") is None for r in rows
            ):
                runtime[name] = {
                    "executed_cases": len(rows),
                    "scope": "Cold per-case process timing unavailable for batch runs; "
                    "see session wall time and stage elapsed times.",
                }
                continue
            seconds = sum(
                r["performance"]["stages"][name].get("process_wall_seconds", 0) for r in rows
            )
            duration = sum(r["performance"]["audio_seconds"] for r in rows)
            runtime[name] = {
                "executed_cases": len(rows),
                "process_wall_seconds": seconds,
                "audio_seconds": duration,
                "weighted_process_rtf": seconds / duration,
            }
    report = {
        "protocol": "music-studio-component-v1",
        "suite_sha256": read_json(output / "session.json").get("suite_sha256")
        if (output / "session.json").exists()
        else None,
        "selected_cases": len(cases),
        "scored_cases": len(scored),
        "missing_cases": missing,
        "scoring_errors": scoring_errors,
        "summary": grouped,
        "cases": scored,
        "runtime": runtime,
        "training_overlap": read_json(output / "session.json").get("training_overlap")
        if (output / "session.json").exists()
        else None,
        "scope": "Engineering subset; different domains are never pooled into one accuracy score.",
    }
    write_json(output / "report.json", report)
    return report


class GpuMonitor:
    """System-wide samples include the display/other processes; not allocator memory."""

    def __init__(self):
        self.stop = threading.Event()
        self.samples = []
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            try:
                probe = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if probe.returncode == 0:
                    memory, utilization = map(float, probe.stdout.splitlines()[0].split(","))
                    self.samples.append(
                        {"time": time.time(), "memory_mb": memory, "utilization": utilization}
                    )
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                pass
            self.stop.wait(1)

    def summary(self):
        return {
            "sample_count": len(self.samples),
            "interval_seconds": 1,
            "peak_device_used_mb": max((s["memory_mb"] for s in self.samples), default=None),
            "idle_device_used_mb": self.samples[0]["memory_mb"] if self.samples else None,
            "note": "Whole GPU at 1 Hz, includes display/other processes; can miss short peaks.",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "validate", "run", "score"])
    parser.add_argument("--manifest", type=Path, default=ROOT / "benchmarks/suite-v1.json")
    parser.add_argument("--data", type=Path, default=ROOT / ".artifacts/benchmark/data")
    parser.add_argument("--output", type=Path, default=ROOT / ".artifacts/benchmark/runs/baseline")
    parser.add_argument("--smoke", action="store_true", help="Ten fixed cases covering all domains")
    parser.add_argument("--case", action="append", help="Select one or more frozen case IDs")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--model-dir", type=Path, default=ROOT / ".cache/models")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--asr-model")
    parser.add_argument(
        "--settings", type=Path, default=ROOT / "benchmarks/experiments/baseline-v1.json"
    )
    parser.add_argument("--asr-revision")
    parser.add_argument("--pitch-backend", choices=["crepe", "pyin"])
    args = parser.parse_args()
    manifest = read_json(args.manifest)
    if args.command == "prepare":
        prepare(manifest, args.data)
    if args.command in ("prepare", "validate", "run"):
        inventory = validate_suite(manifest, args.data)
        print(f"Validated {len(inventory['cases'])} annotated audio cases", flush=True)
    if args.command in ("run", "score"):
        cases = selected_cases(manifest, args)
        config = read_json(args.settings)
        config.update(device=args.device, model_dir=str(args.model_dir), offline=args.offline)
        if args.asr_model:
            if args.asr_model != config.get("asr_model"):
                config["asr_revision"] = args.asr_revision
            config["asr_model"] = args.asr_model
        if args.asr_revision:
            config["asr_revision"] = args.asr_revision
        if args.pitch_backend:
            config["pitch_backend"] = args.pitch_backend
        settings = Settings(**config)
        if args.command == "run":
            engine_path = freeze_engine(args.output)
            started = time.perf_counter()
            monitor = GpuMonitor()
            monitor.thread.start()
            failures = []
            try:
                for index, case in enumerate(cases, 1):
                    print(f"[{index}/{len(cases)}] {case['id']} ({case['domain']})", flush=True)
                    try:
                        run_case(case, args.data, args.output, settings, engine_path)
                    except Exception as error:
                        failures.append({"id": case["id"], "error": str(error)})
                        print(f"  FAILED: {error}", flush=True)
            finally:
                monitor.stop.set()
                monitor.thread.join(timeout=4)
                write_json(
                    args.output / "session.json",
                    {
                        "protocol": "music-studio-component-v1",
                        "suite_sha256": sha256(args.manifest),
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                        "settings": settings.resolved().model_dump(),
                        "packages": installed_versions(
                            [
                                "torch",
                                "torchaudio",
                                "demucs",
                                "faster-whisper",
                                "ctranslate2",
                                "torchcrepe",
                                "librosa",
                                "mir_eval",
                            ]
                        ),
                        "selected_ids": [c["id"] for c in cases],
                        "failures": failures,
                        "wall_seconds": round(time.perf_counter() - started, 3),
                        "gpu": monitor.summary(),
                    },
                )
        report = report_scores(cases, args.data, args.output)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        print(
            f"Scored {report['scored_cases']}/{report['selected_cases']}; "
            f"report: {args.output / 'report.json'}"
        )
        if report["missing_cases"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
