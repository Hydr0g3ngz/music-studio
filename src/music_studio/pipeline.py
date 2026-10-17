import importlib.metadata
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from filelock import FileLock, Timeout

from . import __version__
from .audio import decode_audio
from .config import Settings
from .export import export_project, link_words
from .io import fingerprint, read_json, sha256, write_json
from .schema import AudioInfo, Harmony, Lyrics, Melody, Project, Rhythm

STAGES = ["separate", "lyrics", "melody", "rhythm", "harmony"]
STAGE_SETTINGS = {
    "separate": ["separation_model", "segment_seconds", "mixture_consistency", "device"],
    "lyrics": [
        "asr_model",
        "asr_revision",
        "asr_segmentation",
        "asr_backend",
        "lyrics_input",
        "lyrics_alignment",
        "anchor_model",
        "seed",
        "language",
        "device",
    ],
    "melody": ["pitch_backend", "pitch_threshold", "melody_decoder", "seed", "device"],
    "rhythm": ["rhythm_backend", "rhythm_checkpoint", "device"],
    "harmony": ["harmony_backend"],
}
STAGE_PACKAGES = {
    "separate": ["demucs", "torch", "torchaudio"],
    "lyrics": ["faster-whisper", "ctranslate2"],
    "melody": ["torchcrepe", "torch", "librosa"],
    "rhythm": ["librosa", "beat-this", "torch"],
    "harmony": ["librosa"],
}


def installed_versions(names) -> dict:
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def cache_valid(output: Path, record: dict, signature: str) -> bool:
    if record.get("signature") != signature or not record.get("artifacts"):
        return False
    for relative, digest in record["artifacts"].items():
        path = (output / relative).resolve()
        if not path.is_relative_to(output.resolve()) or not path.is_file():
            return False
        if sha256(path) != digest:
            return False
    return True


class AnalysisCancelled(RuntimeError):
    """A user stopped an analysis; completed stages can still be resumed."""


def run_worker(request: dict, log_path: Path, cancel_event: threading.Event | None = None) -> dict:
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("Analysis cancelled")
    request_path = log_path.with_suffix(".request.json")
    write_json(request_path, request)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        environment = os.environ.copy()
        environment["PYTHONUTF8"] = "1"
        if request.get("engine_path"):
            # Benchmarks freeze the engine so ongoing development cannot change a run.
            environment["PYTHONPATH"] = str(Path(request["engine_path"]).resolve())
        else:
            environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        from .lyric_models import runtime_python

        python = (
            runtime_python(request["settings"])
            if request["stage"] in ("lyrics", "align", "retry", "align_batch", "lyrics_batch")
            else None
        ) or sys.executable
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [python, "-m", "music_studio.worker", str(request_path)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            creationflags=flags,
        )
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise AnalysisCancelled("Analysis cancelled")
                try:
                    return_code = process.wait(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise
    if return_code:
        tail = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
        raise RuntimeError(
            f"Stage '{request['stage']}' failed (exit {return_code}). Log: {log_path}\n{tail}"
        )
    return read_json(Path(request["result"]))


def analyze(
    source: Path,
    output: Path,
    settings: Settings,
    *,
    resume=False,
    progress=print,
    cancel_event: threading.Event | None = None,
) -> Project:
    source, output = source.resolve(), output.resolve()
    if not source.is_file():
        raise ValueError(f"Audio file does not exist: {source}")
    if source.is_relative_to(output):
        raise ValueError("Input must be outside the output directory")
    output.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(output / ".music-studio.lock"))
    try:
        with lock.acquire(timeout=0):
            return _analyze(source, output, settings.resolved(), resume, progress, cancel_event)
    except Timeout:
        raise RuntimeError("Another Music Studio process is using this output directory") from None


def _analyze(
    source: Path,
    output: Path,
    settings: Settings,
    resume: bool,
    progress,
    cancel_event: threading.Event | None = None,
) -> Project:
    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise AnalysisCancelled("Analysis cancelled")

    state_path = output / "run.json"
    existing = read_json(state_path) if state_path.exists() else None
    contents = [p for p in output.iterdir() if p.name != ".music-studio.lock"]
    if contents and not existing:
        raise ValueError("Output is not an empty directory or an existing Music Studio project")
    if existing and not resume:
        raise ValueError("Project already exists. Use --resume or choose a new output directory")
    digest = sha256(source)
    if existing and existing.get("source_sha256") != digest:
        raise ValueError("This output belongs to different audio. Choose a new output directory")
    dependencies = installed_versions(["demucs", "faster-whisper", "torch", "torchaudio"])
    missing = [name for name, version in dependencies.items() if not version]
    if settings.pitch_backend == "crepe" and not installed_versions(["torchcrepe"])["torchcrepe"]:
        missing.append("torchcrepe")
    if missing:
        raise RuntimeError(
            f"Missing inference dependencies: {', '.join(missing)}. "
            "Install this project with the [inference] extra; see README."
        )
    state = existing or {"source_sha256": digest, "stages": {}}
    state.update(status="running", settings=settings.model_dump(), error=None)
    write_json(state_path, state)
    config = settings.model_dump()
    package_root = Path(__file__).parent
    code_signature = fingerprint(
        {
            str(path.relative_to(package_root)): sha256(path)
            for path in sorted(package_root.rglob("*.py"))
            if path.relative_to(package_root).parts[0] != "ui"
        }
    )
    try:
        check_cancelled()
        prepare_signature = fingerprint(
            {
                "source": digest,
                "version": __version__,
                "code": code_signature,
                "rate": 44100,
            }
        )
        prepare = state["stages"].get("decode", {})
        info_path = output / ".state/audio.json"
        if cache_valid(output, prepare, prepare_signature):
            info = AudioInfo.model_validate(read_json(info_path))
            progress("[cache] decode")
        else:
            progress("[1/6] decode audio")
            info = decode_audio(source, output / "audio/source.wav", digest)
            write_json(info_path, info.model_dump())
            state["stages"]["decode"] = {
                "signature": prepare_signature,
                "artifacts": {
                    p: sha256(output / p) for p in ["audio/source.wav", ".state/audio.json"]
                },
            }
            write_json(state_path, state)
        source_hash = sha256(output / "audio/source.wav")
        for index, stage in enumerate(STAGES, 2):
            check_cancelled()
            if stage in ("separate", "rhythm"):
                inputs = {"source": source_hash}
            elif stage in ("lyrics", "melody"):
                inputs = {"vocals": sha256(output / "audio/vocals.wav")}
                if stage == "lyrics" and config.get("lyrics_input") == "source":
                    inputs["source"] = source_hash
                if stage == "lyrics" and config.get("lyrics_python"):
                    from .lyric_models import runtime_identity

                    inputs["runtime"] = runtime_identity(config)
                if stage == "lyrics" and Path(config["asr_model"]).is_dir():
                    inputs["local_model"] = fingerprint(
                        {
                            str(path.relative_to(config["asr_model"])): sha256(path)
                            for path in sorted(Path(config["asr_model"]).rglob("*"))
                            if path.is_file()
                        }
                    )
            else:
                inputs = {
                    "instrumental": sha256(output / "audio/instrumental.wav"),
                    "rhythm": sha256(output / "analysis/rhythm.json"),
                }
            signature = fingerprint(
                {
                    "inputs": inputs,
                    "engine": __version__,
                    "code": code_signature,
                    "settings": {k: config[k] for k in STAGE_SETTINGS[stage]},
                    "dependencies": installed_versions(STAGE_PACKAGES[stage]),
                }
            )
            old_record = state["stages"].get(stage, {})
            if cache_valid(output, old_record, signature):
                progress(f"[cache] {stage}")
                continue
            progress(f"[{index}/6] {stage} (details: logs/{stage}.log)")
            state.update(active_stage=stage)
            write_json(state_path, state)
            result_path = output / "analysis" / f"{stage}.json"
            wall_start = time.perf_counter()
            request = {
                "stage": stage,
                "output": str(output),
                "settings": config,
                "result": str(result_path),
            }
            worker_options = {"cancel_event": cancel_event} if cancel_event is not None else {}
            result = run_worker(request, output / "logs" / f"{stage}.log", **worker_options)
            artifacts = [f"analysis/{stage}.json"]
            if stage == "separate":
                artifacts += result["files"]
            if stage == "melody":
                artifacts += ["analysis/pitch.json"]
            metrics = read_json(result_path.with_suffix(".metrics.json"))
            state["stages"][stage] = {
                "signature": signature,
                "artifacts": {p: sha256(output / p) for p in artifacts},
                "metrics": metrics,
                "wall_seconds": round(time.perf_counter() - wall_start, 3),
            }
            write_json(state_path, state)
        lyrics = Lyrics.model_validate(read_json(output / "analysis/lyrics.json"))
        melody = Melody.model_validate(read_json(output / "analysis/melody.json"))
        rhythm = Rhythm.model_validate(read_json(output / "analysis/rhythm.json"))
        harmony = Harmony.model_validate(read_json(output / "analysis/harmony.json"))
        # Resampling can round duration by < 1 analysis sample. Clamp to master samples.
        for interval in [*lyrics.segments, *melody.notes, *harmony.chords]:
            interval.end = min(interval.end, info.duration)
        for line in lyrics.segments:
            for word in line.words:
                word.end = min(word.end, info.duration)
        rhythm.beats = [t for t in rhythm.beats if t < info.duration]
        link_words(melody, lyrics)
        assets = {
            "source": "audio/source.wav",
            "vocals": "audio/vocals.wav",
            "instrumental": "audio/instrumental.wav",
            "pitch": "analysis/pitch.json",
            "midi": "exports/melody.mid",
            "lrc": "exports/lyrics.lrc",
            "srt": "exports/lyrics.srt",
            "chords": "exports/chords.csv",
            "beats": "exports/beats.csv",
        }
        project = Project(
            audio=info,
            lyrics=lyrics,
            melody=melody,
            rhythm=rhythm,
            harmony=harmony,
            assets=assets,
            settings=config,
            stages=state["stages"],
            warnings=read_json(output / "analysis/separate.json").get("warnings", []),
        )
        # Revalidate after linking/clamping: assignment itself does not validate nested models.
        project = Project.model_validate(project.model_dump())
        export_project(project, output)
        write_json(output / "project.json", project.model_dump())
        state.update(status="complete", active_stage=None, error=None)
        write_json(state_path, state)
        progress(f"Complete: {output / 'project.json'}")
        return project
    except BaseException as error:
        state.update(
            status="cancelled"
            if isinstance(error, (KeyboardInterrupt, AnalysisCancelled))
            else "failed"
        )
        state["error"] = str(error) or type(error).__name__
        write_json(state_path, state)
        raise
