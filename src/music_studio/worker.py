"""Each invocation owns one inference stage. Process exit releases all GPU runtimes."""

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

from .io import read_json, write_json


def execute(request: dict) -> dict:
    if request["stage"] == "lyrics_batch":
        import copy

        os.environ["MUSIC_STUDIO_REUSE_RECOGNIZER"] = "1"
        os.environ["MUSIC_STUDIO_REUSE_ALIGNER"] = "1"
        cases = {}
        for item in request["requests"]:
            try:
                native = copy.deepcopy(item)
                native["stage"] = "lyrics"
                native["settings"]["lyrics_alignment"] = "native"
                lyrics = execute(native)
                output = Path(item["output"])
                write_json(output / "analysis/lyrics-input.json", lyrics)
                metrics_path = Path(item["result"]).with_suffix(".metrics.json")
                write_json(metrics_path.with_suffix(".recognition.json"), read_json(metrics_path))
                cases[item["case_id"]] = {"id": item["case_id"], "status": "complete"}
            except Exception as error:
                traceback.print_exc()
                cases[item["case_id"]] = {
                    "id": item["case_id"],
                    "status": "failed",
                    "error": str(error),
                }
        from .inference_cache import clear_models

        clear_models()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        for item in request["requests"]:
            if cases[item["case_id"]]["status"] != "complete":
                continue
            if item["settings"].get("lyrics_alignment", "native") != "native":
                try:
                    alignment = copy.deepcopy(item)
                    alignment["stage"] = "align"
                    execute(alignment)
                    path = Path(item["result"]).with_suffix(".metrics.json")
                    native = read_json(path.with_suffix(".recognition.json"))
                    aligned = read_json(path)
                    write_json(
                        path,
                        {
                            **aligned,
                            "elapsed_seconds": native["elapsed_seconds"]
                            + aligned["elapsed_seconds"],
                            "torch_peak_allocated_mb": max(
                                native["torch_peak_allocated_mb"] or 0,
                                aligned["torch_peak_allocated_mb"] or 0,
                            ),
                            "recognition_elapsed_seconds": native["elapsed_seconds"],
                            "alignment_elapsed_seconds": aligned["elapsed_seconds"],
                            "model_loading": "shared ASR and aligner phases; warm cases",
                        },
                    )
                except Exception as error:
                    traceback.print_exc()
                    cases[item["case_id"]].update(status="failed", error=str(error))
        result = {"cases": list(cases.values()), "model_loading": "shared models; warm cases"}
        write_json(Path(request["result"]), result)
        return result
    if request["stage"] == "align_batch":
        os.environ["MUSIC_STUDIO_REUSE_ALIGNER"] = "1"
        cases = []
        for item in request["requests"]:
            try:
                execute(item)
                cases.append({"id": item["case_id"], "status": "complete"})
            except Exception as error:
                traceback.print_exc()
                cases.append({"id": item["case_id"], "status": "failed", "error": str(error)})
        result = {"cases": cases, "model_loading": "shared aligner; warm after first case"}
        write_json(Path(request["result"]), result)
        return result
    config = request["settings"]
    os.environ["TORCH_HOME"] = str(Path(config["model_dir"]) / "torch")
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    if config["offline"]:
        os.environ["HF_HUB_OFFLINE"] = "1"
    import random

    from .acceleration import prepare_cuda_libraries

    prepare_cuda_libraries()
    import numpy as np
    import torch

    random.seed(config.get("seed", 0))
    np.random.seed(config.get("seed", 0))
    torch.manual_seed(config.get("seed", 0))

    torch.set_num_threads(config["threads"])
    if config["offline"]:

        def reject_download(*args, **kwargs):
            raise RuntimeError(
                "Model missing in offline mode. Run 'music-studio models download' first."
            )

        torch.hub.download_url_to_file = reject_download
    stage = request["stage"]
    device = config["device"]
    if (
        stage in ("harmony", "download")
        or (stage == "rhythm" and config.get("rhythm_backend", "librosa") != "beat_this")
        or (stage == "melody" and config["pitch_backend"] == "pyin")
    ):
        device = "cpu"
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Check 'music-studio doctor' or use --device cpu.")
    config["device"] = device
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    output = Path(request["output"])
    config["_progress_path"] = str(output / "analysis/progress.json")
    start = time.perf_counter()
    if stage == "separate":
        from .backends.separation import separate

        result = separate(output / "audio/source.wav", output, config)
    elif stage == "lyrics":
        from .backends.lyrics import transcribe

        if config.get("lyrics_alignment") == "anchors":
            config["_anchor_guide"] = str(output / "analysis/anchor-guide.json")
            config["_anchor_audio"] = str(output / "audio/vocals.wav")
        result = transcribe(
            output / f"audio/{config.get('lyrics_input', 'vocals')}.wav", config
        ).model_dump()
    elif stage == "align":
        from .backends.lyric_alignment import align_lyrics, align_reference
        from .schema import Lyrics

        lyrics = Lyrics.model_validate(read_json(output / "analysis/lyrics-input.json"))
        if config.get("lyrics_alignment") == "anchors":
            from .backends.lyric_anchors import align_anchors

            config["_anchor_guide"] = str(output / "analysis/anchor-guide.json")
            result = align_anchors(
                output / "audio/vocals.wav",
                lyrics,
                config,
                preserve_lines=bool(request.get("preserve_lines")),
            ).model_dump()
        else:
            aligner = align_reference if request.get("reference") else align_lyrics
            audio_name = request.get("align_input", "vocals")
            if audio_name not in ("vocals", "source"):
                raise ValueError("Unknown alignment audio")
            result = aligner(output / f"audio/{audio_name}.wav", lyrics, config).model_dump()
    elif stage == "melody":
        from .backends.melody import extract_melody

        result = extract_melody(output / "audio/vocals.wav", output, config).model_dump()
    elif stage == "retry":
        from .backends.lyric_retry import retry_line
        from .schema import Lyrics

        lyrics = Lyrics.model_validate(read_json(output / "analysis/lyrics-input.json"))
        result = retry_line(
            output / f"audio/{config.get('lyrics_input', 'vocals')}.wav",
            lyrics,
            request["line_id"],
            output,
            config,
        ).model_dump()
    elif stage == "rhythm":
        from .backends.rhythm import estimate_rhythm

        result = estimate_rhythm(output / "audio/source.wav", config).model_dump()
    elif stage == "harmony":
        from .backends.harmony import estimate_harmony
        from .schema import Rhythm

        rhythm = Rhythm.model_validate(read_json(output / "analysis/rhythm.json"))
        result = estimate_harmony(output / "audio/instrumental.wav", rhythm, config).model_dump()
    elif stage == "download":
        from demucs.pretrained import get_model

        get_model(config["separation_model"])
        if config.get("asr_backend", "whisper") == "whisper":
            from faster_whisper import WhisperModel

            WhisperModel(
                config["asr_model"],
                device="cpu",
                compute_type="int8",
                download_root=str(Path(config["model_dir"]) / "whisper"),
                local_files_only=config["offline"],
                revision=config["asr_revision"],
            )
        else:
            from .lyric_models import model_path

            model_path(config["asr_backend"], config)
        result = {"downloaded": [config["separation_model"], config["asr_model"]]}
        if config.get("lyrics_alignment") == "qwen":
            from .lyric_models import model_path

            model_path("aligner", config)
            result["downloaded"].append("Qwen3-ForcedAligner-0.6B")
        if config.get("lyrics_alignment") in ("anchors", "whisper"):
            from faster_whisper import WhisperModel

            from .backends.lyric_anchors import GUIDES

            guide = config.get("anchor_model", "small")
            models = ["small", "large-v3-turbo"] if guide == "dual" else [guide]
            if config.get("lyrics_alignment") == "whisper":
                models = ["small"]
            for model in models:
                WhisperModel(
                    model,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(Path(config["model_dir"]) / "whisper"),
                    local_files_only=config["offline"],
                    revision=GUIDES[model],
                )
                result["downloaded"].append(f"Whisper {model} timing guide")
        if config.get("rhythm_backend") == "beat_this":
            from .beat_models import beat_checkpoint

            beat_checkpoint(config)
            result["downloaded"].append(f"beat_this/{config['rhythm_checkpoint']}")
    else:
        raise ValueError(f"Unknown stage: {stage}")
    result_path = Path(request["result"])
    write_json(result_path, result)
    metrics = {
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "device": device,
        "torch_peak_allocated_mb": (
            round(torch.cuda.max_memory_allocated() / 1024**2, 1) if device == "cuda" else None
        ),
        "memory_note": "PyTorch allocator only; CTranslate2 memory is not included.",
    }
    if stage in ("lyrics", "align", "retry"):
        import importlib.metadata

        metrics["runtime_python"] = sys.executable
        metrics["runtime_packages"] = {}
        for package in ("torch", "transformers", "qwen-asr", "faster-whisper", "ctranslate2"):
            try:
                metrics["runtime_packages"][package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                pass
    write_json(result_path.with_suffix(".metrics.json"), metrics)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        execute(read_json(args.request))
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
