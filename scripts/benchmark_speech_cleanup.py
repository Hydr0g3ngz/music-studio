"""Evaluate the frozen paired speech pilot. Audio stays outside the repository."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from pystoi import stoi
from scipy.signal import correlate

from music_studio.io import sha256
from music_studio.studio.cleanup import WEIGHTS, enhance, resample_channel

FROZEN_SHA256 = "1efa1d8fa4e49ff0b25049f3c1cd08d052cc2d0c55ce74ea0b1e67bb1c5e88e5"
VALIDATION_SHA256 = "1c49f145356c51f181b9f1a14d7d1389f2d35cd4944c85f460fe1118902bdba3"


def si_sdr(reference, estimate):
    reference = reference.astype(np.float64) - np.mean(reference)
    estimate = estimate.astype(np.float64) - np.mean(estimate)
    power = float(np.dot(reference, reference))
    if power < 1e-9:
        raise ValueError("Reference is too quiet for SI-SDR")
    projected = reference * (np.dot(reference, estimate) / power)
    return float(
        10
        * np.log10((np.sum(projected**2) + 1e-12) / (np.sum((estimate - projected) ** 2) + 1e-12))
    )


def scores(reference, estimate, rate):
    return {
        "si_sdr_db": si_sdr(reference, estimate),
        "stoi": float(stoi(reference, estimate, rate)),
    }


def evaluate(data_dir, model_dir, destination, model="gtcrn", suite="pilot"):
    root = Path(__file__).resolve().parents[1]
    manifest_file = root / (
        "benchmarks/speech-cleanup-v1.json"
        if suite == "pilot"
        else "benchmarks/speech-cleanup-validation-v1.json"
    )
    frozen_hash = FROZEN_SHA256 if suite == "pilot" else VALIDATION_SHA256
    assert hashlib.sha256(manifest_file.read_bytes()).hexdigest() == frozen_hash
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if suite == "validation":
        frozen = manifest["candidates"][model]
        for key, field in (("rate", "internal_rate"), ("hop", "hop"), ("padding", "tail_padding")):
            assert WEIGHTS[model][key] == frozen[field], "Freeze a new protocol for changed DSP"
        assert frozen["strength"] == 1
        if model == "dpdfnet2-48k":
            assert frozen["attenuation_limit_db"] == 12
    work = destination.parent / (destination.stem + "-audio")
    if destination.exists() or work.exists():
        raise ValueError("Use a fresh result path; do not overwrite an experiment")
    work.mkdir(parents=True)
    results = []
    for sample in manifest["samples"]:
        name = sample["id"] + ".wav"
        clean, noisy = data_dir / "clean" / name, data_dir / "noisy" / name
        assert sha256(clean) == sample["clean"]["sha256"]
        assert sha256(noisy) == sample["noisy"]["sha256"]
        reference, rate = sf.read(clean, dtype="float32", always_2d=True)
        raw, raw_rate = sf.read(noisy, dtype="float32", always_2d=True)
        assert rate == raw_rate and reference.shape == raw.shape and raw.shape[1] == 1
        started = time.perf_counter()
        output = work / (sample["id"] + "-enhanced.wav")
        report = enhance(noisy, output, model_dir, strength=1, threads=2, model=model)
        seconds = time.perf_counter() - started
        enhanced, output_rate = sf.read(output, dtype="float32", always_2d=True)
        assert output_rate == rate and enhanced.shape == raw.shape
        assert np.isfinite(enhanced).all()
        assert sha256(clean) == sample["clean"]["sha256"]
        assert sha256(noisy) == sample["noisy"]["sha256"]
        ref16, raw16, out16 = [
            resample_channel(a[:, 0], rate, 16000) for a in (reference, raw, enhanced)
        ]
        baseline16, processed16 = scores(ref16, raw16, 16000), scores(ref16, out16, 16000)
        baseline_native, processed_native = (
            scores(reference[:, 0], raw[:, 0], rate),
            scores(reference[:, 0], enhanced[:, 0], rate),
        )
        correlation = correlate(out16, ref16, mode="full", method="fft")
        center = len(ref16) - 1
        lag = int(np.argmax(correlation[center - 320 : center + 321]) - 320)
        clean_output = work / (sample["id"] + "-clean-control.wav")
        enhance(clean, clean_output, model_dir, strength=1, threads=2, model=model)
        controlled, control_rate = sf.read(clean_output, dtype="float32", always_2d=True)
        assert control_rate == rate and controlled.shape == reference.shape
        assert sha256(clean) == sample["clean"]["sha256"]
        control16 = resample_channel(controlled[:, 0], rate, 16000)
        result = {
            "id": sample["id"],
            "speaker": sample["speaker"],
            "duration_seconds": len(raw) / rate,
            "sample_rate": rate,
            "channels": 1,
            "frames": len(raw),
            "input_sha256": sample["noisy"]["sha256"],
            "clean_sha256": sample["clean"]["sha256"],
            "output_sha256": sha256(output),
            "speech_16k": {
                "baseline": baseline16,
                "processed": processed16,
                "delta": {k: processed16[k] - baseline16[k] for k in baseline16},
            },
            "native_rate": {
                "baseline": baseline_native,
                "processed": processed_native,
                "delta": {k: processed_native[k] - baseline_native[k] for k in baseline_native},
            },
            "clean_control_16k": scores(ref16, control16, 16000),
            "diagnostic_lag_samples_16k": lag,
            "seconds_including_model_load_and_metering": seconds,
            "rtf": seconds / (len(raw) / rate),
            "loudness": {
                "before": report["before"]["integrated_lufs"],
                "after": report["after"]["integrated_lufs"],
            },
        }
        results.append(result)
        print(
            json.dumps(
                {
                    "id": result["id"],
                    "delta": result["speech_16k"]["delta"],
                    "lag": lag,
                    "rtf": result["rtf"],
                }
            ),
            flush=True,
        )
    summary = {}
    for band in ("speech_16k", "native_rate"):
        summary[band] = {
            metric: {
                "baseline_mean": statistics.mean(r[band]["baseline"][metric] for r in results),
                "processed_mean": statistics.mean(r[band]["processed"][metric] for r in results),
                "delta_mean": statistics.mean(r[band]["delta"][metric] for r in results),
                "delta_median": statistics.median(r[band]["delta"][metric] for r in results),
                "regressions": [r["id"] for r in results if r[band]["delta"][metric] < 0],
            }
            for metric in ("si_sdr_db", "stoi")
        }
    output = {
        "date": "2026-10-16",
        "scope": manifest["purpose"],
        "manifest_sha256": frozen_hash,
        "suite": suite,
        "model_sha256": WEIGHTS[model]["sha256"],
        "model": model + " (official Sherpa-ONNX export)",
        "attenuation_limit_db": 12 if model == "dpdfnet2-48k" else None,
        "strength": 1,
        "threads": 2,
        "device": "cpu",
        "platform": platform.platform(),
        "cpu": platform.processor(),
        "versions": {
            p: importlib.metadata.version(p)
            for p in ("sherpa-onnx", "pyebur128", "av", "pystoi", "numpy", "scipy")
        },
        "method": "Full paired files; no lag/gain fitting. Native-rate and 16 kHz metrics "
        "both retained. Model padding is fixed before inference. "
        "Clean controls assess unwanted alteration.",
        "limits": manifest["limits"]
        + [
            "No confidence interval from only two speaker clusters",
            "Not directly comparable to published full-testset results",
            "STOI and SI-SDR do not replace listening tests",
        ],
        "summary": summary,
        "clean_control_16k_mean": {
            metric: statistics.mean(r["clean_control_16k"][metric] for r in results)
            for metric in ("si_sdr_db", "stoi")
        },
        "by_speaker": {
            speaker: {
                metric: statistics.mean(
                    r["speech_16k"]["delta"][metric] for r in results if r["speaker"] == speaker
                )
                for metric in ("si_sdr_db", "stoi")
            }
            for speaker in ("p232", "p257")
        },
        "rtf_median": statistics.median(r["rtf"] for r in results),
        "max_absolute_diagnostic_lag_samples_16k": max(
            abs(r["diagnostic_lag_samples_16k"]) for r in results
        ),
        "structure": "Exact rate/channels/length, finite output and unchanged source hashes "
        "passed for all samples",
        "samples": results,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "rtf_median": output["rtf_median"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=list(WEIGHTS), default="gtcrn")
    parser.add_argument("--suite", choices=["pilot", "validation"], default="pilot")
    args = parser.parse_args()
    evaluate(args.data_dir, args.model_dir, args.output, args.model, args.suite)
