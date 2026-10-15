"""Streaming mono/stereo loudness and true peak using libebur128, not RMS."""

import math
from pathlib import Path

import numpy as np
import soundfile as sf


def _finite(value):
    return float(value) if math.isfinite(value) else None


def _db(value):
    return 20 * math.log10(value) if value > 0 else None


def measure(path: Path) -> dict:
    try:
        import pyebur128 as ebu
    except ImportError as error:
        raise ValueError("Loudness runtime is missing; run scripts/setup-next.ps1") from error

    with sf.SoundFile(path) as source:
        if source.channels not in (1, 2):
            raise ValueError("Loudness measurement currently supports mono or stereo audio")
        mode = (
            ebu.MeasurementMode.MODE_I
            | ebu.MeasurementMode.MODE_LRA
            | ebu.MeasurementMode.MODE_TRUE_PEAK
            | ebu.MeasurementMode.MODE_HISTOGRAM
        )
        state = ebu.R128State(source.channels, source.samplerate, mode)
        frames = 0
        for block in source.blocks(blocksize=65536, dtype="float32", always_2d=True):
            if not np.isfinite(block).all():
                raise ValueError("Audio contains non-finite samples")
            state.add_frames(np.ascontiguousarray(block.reshape(-1)), len(block))
            frames += len(block)
        duration = frames / source.samplerate
        integrated = _finite(ebu.get_loudness_global(state)) if duration >= 0.4 else None
        lra = _finite(ebu.get_loudness_range(state)) if duration >= 3 else None
        sample_peaks = [ebu.get_sample_peak(state, ch) for ch in range(source.channels)]
        # Flush the FIR's tail only after reading loudness. Padding is not part
        # of the programme and must not alter the integrated loudness or LRA.
        state.add_frames(np.zeros(512 * source.channels, dtype=np.float32), 512)
        true_peaks = [ebu.get_true_peak(state, ch) for ch in range(source.channels)]
        return {
            "integrated_lufs": integrated,
            "true_peak_dbtp": _db(max(true_peaks, default=0)),
            "sample_peak_dbfs": _db(max(sample_peaks, default=0)),
            "loudness_range_lu": lra,
            "loudness_range_stable": duration >= 60 and lra is not None,
            "channel_true_peaks_dbtp": [_db(p) for p in true_peaks],
            "frames": frames,
            "sample_rate": source.samplerate,
            "channels": source.channels,
            "duration": duration,
            "backend": "libebur128 " + ebu.get_libebur128_version(),
            "algorithm": "ITU-R BS.1770 gated integrated loudness; libebur128 true peak",
            "unmeasurable_reason": (
                "shorter_than_400ms"
                if duration < 0.4
                else "below_gate"
                if integrated is None
                else None
            ),
            "notes": ["LRA is provisional before 60 seconds"] if duration < 60 else [],
        }


def normalization_gain(levels: dict, target_lufs: float, ceiling_dbtp: float) -> dict:
    integrated, peak = levels["integrated_lufs"], levels["true_peak_dbtp"]
    if integrated is None or peak is None:
        raise ValueError("Cannot normalize silence, below-gate audio or a clip shorter than 400 ms")
    requested = target_lufs - integrated
    # Static gain preserves dynamics; it is not a limiter. Keep a small margin
    # for FLOAT rounding, then verify the rendered result with the same meter.
    allowed = ceiling_dbtp - peak - 0.01
    applied = min(requested, allowed)
    if applied < -120:
        raise ValueError("Audio level is outside the supported normalization range")
    return {
        "requested_gain_db": requested,
        "applied_gain_db": applied,
        "target_lufs": target_lufs,
        "ceiling_dbtp": ceiling_dbtp,
        "peak_limited": applied < requested - 0.01,
        "method": "Static gain; no compression or limiting",
    }
