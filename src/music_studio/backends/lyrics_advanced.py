"""Optional recognition backends, executed in a separate, pinned inference environment."""

import gc
from pathlib import Path

import numpy as np

from ..audio import load_mono
from ..inference_cache import inference_model
from ..lyric_models import MODELS, model_path
from ..progress import report_progress
from ..schema import LyricLine, Lyrics
from .lyric_alignment import LANGUAGES, align_lyrics


def transcribe_advanced(source: Path, config: dict) -> Lyrics:
    import torch

    audio = load_mono(source, 16000)
    backend = config["asr_backend"]
    if np.max(np.abs(audio), initial=0) < 1e-5:
        return Lyrics(language=config["language"], timing_method="empty", segments=[])
    device = config["device"]
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    language = config.get("language")
    segments = []
    if backend == "qwen":
        from qwen_asr import Qwen3ASRModel

        model = inference_model(
            ("qwen", config["model_dir"], device),
            lambda: Qwen3ASRModel.from_pretrained(
                model_path("qwen", config),
                dtype=dtype,
                device_map="cuda:0" if device == "cuda" else "cpu",
                max_inference_batch_size=1,
                max_new_tokens=2048,
                attn_implementation="sdpa",
                local_files_only=True,
            ),
        )
        # Keep native recognition context within a minute; do not use a speech VAD on singing.
        chunk_samples = 60 * 16000
        for left in range(0, len(audio), chunk_samples):
            right = min(len(audio), left + chunk_samples)
            report_progress(
                config,
                "识别歌词片段",
                left // chunk_samples,
                (len(audio) + chunk_samples - 1) // chunk_samples,
            )
            out = model.transcribe(
                audio=(audio[left:right], 16000), language=LANGUAGES.get(language)
            )[0]
            language = language or next(
                (key for key, name in LANGUAGES.items() if name == out.language), None
            )
            if out.text.strip():
                segments.append(
                    LyricLine(
                        id=f"l{len(segments):04d}",
                        text=out.text.strip(),
                        start=left / 16000,
                        end=right / 16000,
                    )
                )
        del model
        report_progress(config, "歌词识别完成，准备校准时间", 1, 1)
    elif backend == "heart":
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        path = model_path("heart", config)

        def load_heart():
            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                path,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                local_files_only=True,
                attn_implementation="sdpa",
            )
            processor = AutoProcessor.from_pretrained(path, local_files_only=True)
            pipe = pipeline(
                "automatic-speech-recognition",
                model=model,
                tokenizer=processor.tokenizer,
                feature_extractor=processor.feature_extractor,
                device=0 if device == "cuda" else -1,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                chunk_length_s=30,
                batch_size=1,
            )
            return model, processor, pipe

        model, processor, pipe = inference_model(("heart", config["model_dir"], device), load_heart)
        generate = {
            "max_new_tokens": 256,
            "num_beams": 2,
            "task": "transcribe",
            "condition_on_prev_tokens": False,
            "compression_ratio_threshold": 1.8,
            "temperature": (0.0, 0.1, 0.2, 0.4),
            "logprob_threshold": -1.0,
            "no_speech_threshold": 0.4,
        }
        if language:
            generate["language"] = language
        torch.manual_seed(config.get("seed", 0))
        out = pipe(audio, return_timestamps=True, return_language=True, generate_kwargs=generate)
        for chunk in out.get("chunks", []):
            if not language and chunk.get("language"):
                language = next(
                    (
                        code
                        for code, name in LANGUAGES.items()
                        if name.casefold() == chunk["language"].casefold()
                    ),
                    None,
                )
            start, end = chunk["timestamp"]
            start = max(0, float(start or 0))
            end = min(len(audio) / 16000, float(end or len(audio) / 16000))
            if chunk["text"].strip() and end > start:
                segments.append(
                    LyricLine(
                        id=f"l{len(segments):04d}", text=chunk["text"].strip(), start=start, end=end
                    )
                )
        del pipe, model, processor
    else:
        raise ValueError(f"Unknown recognition backend: {backend}")
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    result = Lyrics(
        language=language,
        timing_method=f"{backend}_coarse_segments",
        segments=segments,
        warnings=[f"Recognition: {MODELS[backend][0]}@{MODELS[backend][1]}"],
    )
    if config.get("lyrics_alignment") in ("qwen", "whisper", "anchors"):
        result = align_lyrics(Path(config.get("_anchor_audio", source)), result, config)
    return result
