"""Bounded-memory PCM operations. All ranges are half-open decoded sample ranges."""

from pathlib import Path

import numpy as np
import soundfile as sf

from .models import Balance, Fade, Gain, LoudnessNormalize, Mix, Normalize, Reverse, Trim

BLOCK = 65536


def inspect_audio(path: Path) -> dict:
    peak, energy, dc, samples, clipped = 0.0, 0.0, None, 0, 0
    with sf.SoundFile(path) as source:
        info = {
            "sample_rate": source.samplerate,
            "channels": source.channels,
            "frames": len(source),
            "duration": len(source) / source.samplerate,
        }
        for data in source.blocks(blocksize=BLOCK, dtype="float32", always_2d=True):
            if not np.isfinite(data).all():
                raise ValueError("Audio contains non-finite samples")
            peak = max(peak, float(np.max(np.abs(data), initial=0)))
            energy += float(np.sum(data.astype(np.float64) ** 2))
            total = np.sum(data, axis=0, dtype=np.float64)
            dc = total if dc is None else dc + total
            clipped += int(np.count_nonzero(np.abs(data) >= 1))
            samples += data.size
    rms = float(np.sqrt(energy / samples)) if samples else 0.0
    info.update(
        peak=peak,
        peak_dbfs=20 * float(np.log10(peak)) if peak else None,
        rms_dbfs=20 * float(np.log10(rms)) if rms else None,
        samples_at_or_above_full_scale=clipped,
        dc_offset=(dc / info["frames"]).tolist() if info["frames"] else [],
        measurement="Sample peak and full-file RMS; not LUFS or true peak",
    )
    return info


def peaks(path: Path, bins: int = 1600) -> list[float]:
    with sf.SoundFile(path) as source:
        size = max(1, int(np.ceil(len(source) / bins)))
        return [
            round(float(np.max(np.abs(data), initial=0)), 5)
            for data in source.blocks(blocksize=size, dtype="float32", always_2d=True)
        ]


def balance(data: np.ndarray, pan: float) -> np.ndarray:
    if data.shape[1] != 2:
        raise ValueError("Stereo balance requires a stereo asset")
    # Preserve the original stereo signal exactly at center.
    result = data.copy()
    result[:, 0 if pan > 0 else 1] *= np.cos(abs(pan) * np.pi / 2)
    return result


def process(source: Path, destination: Path, operation, assets: dict[str, Path]) -> dict:
    """Apply one typed operation to a new FLOAT WAV; never modify an input file."""
    if destination.resolve() in {source.resolve(), *(p.resolve() for p in assets.values())}:
        raise ValueError("An output cannot overwrite an input asset")
    destination.parent.mkdir(parents=True, exist_ok=True)
    loudness_details = None
    with sf.SoundFile(source) as original:
        rate, channels, length = original.samplerate, original.channels, len(original)
        start, end = 0, length
        if isinstance(operation, Trim):
            start, end = round(operation.start * rate), round(operation.end * rate)
            if start < 0 or end > length or end <= start:
                raise ValueError("Trim range must fit within the current audio")
        if isinstance(operation, Fade):
            if max(operation.in_seconds, operation.out_seconds) * rate > length + 1:
                raise ValueError("A fade cannot be longer than the current audio")
        scale = 1.0
        if isinstance(operation, Normalize):
            peak = inspect_audio(source)["peak"]
            scale = 10 ** (operation.peak_dbfs / 20) / peak if peak > 1e-12 else 1.0
        if isinstance(operation, LoudnessNormalize):
            from .loudness import measure, normalization_gain

            before = measure(source)
            loudness_details = normalization_gain(
                before, operation.target_lufs, operation.ceiling_dbtp
            )
            loudness_details["before"] = before
            scale = 10 ** (loudness_details["applied_gain_db"] / 20)
        if isinstance(operation, Mix):
            return _mix(destination, operation, assets)
        with sf.SoundFile(
            destination, "w", samplerate=rate, channels=channels, subtype="FLOAT"
        ) as output:
            position = start
            while position < end:
                count = min(BLOCK, end - position)
                if isinstance(operation, Reverse):
                    original.seek(length - position - count)
                    data = original.read(count, dtype="float32", always_2d=True)[::-1].copy()
                else:
                    original.seek(position)
                    data = original.read(count, dtype="float32", always_2d=True)
                if len(data) != count:
                    raise ValueError("Audio changed or was truncated during rendering")
                if isinstance(operation, Gain):
                    data *= 10 ** (operation.db / 20)
                elif isinstance(operation, Normalize | LoudnessNormalize):
                    data *= scale
                elif isinstance(operation, Balance):
                    data = balance(data, operation.pan)
                elif isinstance(operation, Fade):
                    indices = np.arange(position, position + count, dtype=np.float64)
                    envelope = np.ones(count)
                    fade_in, fade_out = (
                        round(operation.in_seconds * rate),
                        round(operation.out_seconds * rate),
                    )
                    if fade_in > 0:
                        envelope *= np.minimum(1, indices / max(1, fade_in - 1))
                    if fade_out > 0:
                        envelope *= np.minimum(1, (length - 1 - indices) / max(1, fade_out - 1))
                    data *= envelope[:, None]
                if not np.isfinite(data).all():
                    raise ValueError("Operation produced non-finite audio")
                output.write(data)
                position += count
    result = {"frames": end - start, "sample_rate": rate, "channels": channels}
    if loudness_details is not None:
        from .loudness import measure

        after = measure(destination)
        if after["true_peak_dbtp"] is not None and after["true_peak_dbtp"] > operation.ceiling_dbtp:
            raise ValueError("Rendered audio exceeds its requested true peak ceiling")
        loudness_details["after"] = after
        result["loudness"] = loudness_details
    return result


def _mix(destination: Path, operation: Mix, assets: dict[str, Path]) -> dict:
    from contextlib import ExitStack

    with ExitStack() as stack:
        inputs = []
        for track in operation.tracks:
            if track.asset not in assets:
                raise ValueError(f"Audio asset is unavailable: {track.asset}")
            inputs.append((track, stack.enter_context(sf.SoundFile(assets[track.asset]))))
        first = inputs[0][1]
        shape = len(first), first.samplerate, first.channels
        if shape[2] != 2 or any((len(f), f.samplerate, f.channels) != shape for _, f in inputs):
            raise ValueError("Mix tracks must have identical stereo sample timelines")
        output = stack.enter_context(
            sf.SoundFile(destination, "w", samplerate=shape[1], channels=2, subtype="FLOAT")
        )
        for start in range(0, shape[0], BLOCK):
            count = min(BLOCK, shape[0] - start)
            mixed = np.zeros((count, 2), dtype=np.float64)
            for track, audio in inputs:
                data = audio.read(count, dtype="float32", always_2d=True)
                if len(data) != count:
                    raise ValueError("Mix input changed during rendering")
                mixed += balance(data, track.pan) * 10 ** (track.gain_db / 20)
            if not np.isfinite(mixed).all():
                raise ValueError("Mix produced non-finite audio")
            output.write(mixed.astype(np.float32))
    return {"frames": shape[0], "sample_rate": shape[1], "channels": shape[2]}


def export_audio(source: Path, destination: Path, subtype: str = "PCM_24") -> dict:
    if source.resolve() == destination.resolve():
        raise ValueError("An export cannot overwrite its input")
    if subtype not in ("PCM_16", "PCM_24", "FLOAT"):
        raise ValueError("Unsupported WAV encoding")
    info = inspect_audio(source)
    if subtype != "FLOAT" and info["peak"] > 1:
        raise ValueError("Output exceeds full scale; normalize or lower gain before integer export")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        sf.SoundFile(source) as audio,
        sf.SoundFile(
            destination, "w", samplerate=audio.samplerate, channels=audio.channels, subtype=subtype
        ) as output,
    ):
        for data in audio.blocks(blocksize=BLOCK, dtype="float32", always_2d=True):
            output.write(data)
    return {**info, "encoding": subtype, "format": "WAV"}
