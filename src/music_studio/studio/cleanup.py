"""Fixed, optional CPU speech enhancement. Downloads happen only via explicit setup."""

import hashlib
import math
import os
import shutil
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

GTCRN_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "speech-enhancement-models/gtcrn_simple.onnx"
)
GTCRN_SHA256 = "e77603ac0c23dac3227dd2d7135b3a585cbee2679048aecfa886657d3ae1b534"
GTCRN_BYTES = 535638
WEIGHTS = {
    "gtcrn": {
        "file": "gtcrn_simple.onnx",
        "sha256": GTCRN_SHA256,
        "bytes": GTCRN_BYTES,
        "rate": 16000,
        "hop": 256,
        "padding": 512,
        "license": "GTCRN-MIT.txt",
    },
    "dpdfnet2-48k": {
        "file": "dpdfnet2_48khz_hr.onnx",
        "sha256": "0b399f8a58dc4d70d8cd97541f5c39869406145193b957d00a03b66070944928",
        "bytes": 10596848,
        "rate": 48000,
        "hop": 480,
        "padding": 4800,
        "license": "DPDFNet-Apache-2.0.txt",
    },
}


def model_path(model_dir, model="gtcrn"):
    if model not in WEIGHTS:
        raise ValueError("Unknown fixed speech cleanup model")
    return Path(model_dir).expanduser().resolve() / "cleanup" / WEIGHTS[model]["file"]


def verify_model(path, model="gtcrn"):
    return (
        path.is_file()
        and path.stat().st_size == WEIGHTS[model]["bytes"]
        and hashlib.sha256(path.read_bytes()).hexdigest() == WEIGHTS[model]["sha256"]
    )


def download(model_dir, model="gtcrn"):
    import urllib.request

    path = model_path(model_dir, model)
    spec = WEIGHTS[model]
    if verify_model(path, model):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix("." + uuid.uuid4().hex + ".part")
    try:
        with (
            urllib.request.urlopen(
                GTCRN_URL.rsplit("/", 1)[0] + "/" + spec["file"], timeout=45
            ) as response,
            temporary.open("wb") as file,
        ):
            while data := response.read(65536):
                file.write(data)
                if file.tell() > spec["bytes"]:
                    raise ValueError("Unexpected speech model size")
        if not verify_model(temporary, model):
            raise ValueError("Speech model checksum failed; the existing cache was not replaced")
        os.replace(temporary, path)
        shutil.copyfile(
            Path(__file__).parent / "licenses" / spec["license"], path.parent / spec["license"]
        )
    finally:
        temporary.unlink(missing_ok=True)
    return path


def resample_channel(samples, source_rate, target_rate, frames=None):
    """Zero-time-aligned resampling, with an explicit tail and exact requested length."""
    if frames is None:
        frames = max(1, round(len(samples) * target_rate / source_rate))
    if source_rate == target_rate:
        if len(samples) < frames:
            raise ValueError("Input is shorter than its requested timeline")
        return np.ascontiguousarray(samples[:frames], dtype=np.float32)
    import av

    padding = math.ceil(64 * source_rate / target_rate) + 64
    data = np.pad(np.asarray(samples, dtype=np.float32), (0, padding))
    frame = av.AudioFrame.from_ndarray(data.reshape(1, -1), format="fltp", layout="mono")
    frame.sample_rate = source_rate
    converter = av.AudioResampler(format="fltp", layout="mono", rate=target_rate)
    converted = converter.resample(frame) + converter.resample(None)
    result = np.concatenate([f.to_ndarray().reshape(-1) for f in converted])
    if len(result) < frames:
        raise ValueError("Resampler did not preserve the requested timeline")
    return np.ascontiguousarray(result[:frames], dtype=np.float32)


def enhance(source, destination, model_dir, strength=1.0, threads=2, model="gtcrn"):
    import sherpa_onnx as sherpa

    from .loudness import measure

    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError("Speech cleanup cannot overwrite its input")
    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("Speech cleanup strength must be between 0 and 1")
    path = model_path(model_dir, model)
    spec = WEIGHTS[model]
    if not verify_model(path, model):
        raise ValueError("Verified speech weights are missing; use the explicit model setup")
    if Path(destination).resolve() == path.resolve():
        raise ValueError("Speech cleanup cannot overwrite model weights")
    signal, rate = sf.read(source, dtype="float32", always_2d=True)
    if signal.shape[1] not in (1, 2) or not len(signal) or not np.isfinite(signal).all():
        raise ValueError("Speech cleanup requires finite, non-empty mono or stereo audio")
    network = (
        {"gtcrn": sherpa.OfflineSpeechDenoiserGtcrnModelConfig(model=str(path))}
        if model == "gtcrn"
        else {
            "dpdfnet": sherpa.OfflineSpeechDenoiserDpdfNetModelConfig(
                model=str(path), attenuation_limit_db=12
            )
        }
    )
    config = sherpa.OfflineSpeechDenoiserConfig(
        model=sherpa.OfflineSpeechDenoiserModelConfig(
            **network,
            provider="cpu",
            num_threads=max(1, min(threads, 8)),
            debug=False,
        )
    )
    if not config.validate():
        raise ValueError("Speech runtime configuration is unavailable")
    denoiser = sherpa.OfflineSpeechDenoiser(config)
    result = np.empty_like(signal)
    for channel in range(signal.shape[1]):
        if channel == 1 and np.array_equal(signal[:, 0], signal[:, 1]):
            # Canonical mono imports have two identical channels. The native
            # backend resets its state per call, so reuse the identical result.
            result[:, 1] = result[:, 0]
            continue
        mono = resample_channel(signal[:, channel], rate, spec["rate"])
        # The offline STFT otherwise truncates a partial final hop. Tail padding
        # lets the model process the last real samples; never pad a missing result.
        padded = np.pad(mono, (0, (-len(mono)) % spec["hop"] + spec["padding"]))
        enhanced = denoiser(np.ascontiguousarray(padded), spec["rate"])
        wet = np.asarray(enhanced.samples, dtype=np.float32)
        if enhanced.sample_rate != spec["rate"] or len(wet) < len(mono):
            raise ValueError("Speech model returned an incomplete timeline")
        wet = resample_channel(wet[: len(mono)], spec["rate"], rate, len(signal))
        result[:, channel] = signal[:, channel] * (1 - strength) + wet * strength
    if not np.isfinite(result).all():
        raise ValueError("Speech model produced non-finite audio")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, result, rate, subtype="FLOAT")
    return {
        "model": model,
        "model_sha256": spec["sha256"],
        "runtime": "sherpa-onnx " + sherpa.__version__,
        "device": "cpu",
        "strength": strength,
        "internal_sample_rate": spec["rate"],
        "attenuation_limit_db": 12 if model == "dpdfnet2-48k" else None,
        "before": measure(source),
        "after": measure(destination),
        "notes": [
            "For speech. Music and ambience may be removed or distorted.",
            "GTCRN removes frequencies above 8 kHz. DPDFNet processes at 48 kHz; "
            "neither model guarantees unaltered speech or music.",
            "Stereo channels are processed independently; the stereo image may change.",
        ],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download"])
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--model", choices=list(WEIGHTS), default="gtcrn")
    arguments = parser.parse_args()
    print(download(arguments.model_dir, arguments.model))
