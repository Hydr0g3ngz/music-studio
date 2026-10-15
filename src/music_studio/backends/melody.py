from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

from ..audio import load_mono
from ..io import write_json
from ..schema import Melody, Note

RATE = 16000
HOP = 160


def _runs(values):
    starts = np.r_[0, np.flatnonzero(np.diff(values)) + 1]
    ends = np.r_[starts[1:], len(values)]
    return zip(starts, ends, strict=False)


def notes_from_contour(
    times: np.ndarray,
    frequencies: np.ndarray,
    scores: np.ndarray,
    duration: float,
    onset_times=(),
    minimum_duration: float = 0.08,
) -> list[Note]:
    """Conservative monophonic transcription; preserve performance time, not a beat grid."""
    if len(times) == 0:
        return []
    step = float(np.median(np.diff(times))) if len(times) > 1 else HOP / RATE
    valid = np.isfinite(frequencies) & (frequencies > 0)
    pitches = np.full(len(times), -1, dtype=int)
    midi = np.zeros(len(times))
    midi[valid] = 69 + 12 * np.log2(frequencies[valid] / 440.0)
    for start, end in _runs(valid.astype(int)):
        if valid[start]:
            pitches[start:end] = np.rint(
                median_filter(midi[start:end], size=5, mode="nearest")
            ).astype(int)
    # Bridge brief confidence dropouts/jitter only when both neighbors agree.
    for start, end in list(_runs(pitches)):
        if (end - start) * step <= 0.04 and start > 0 and end < len(pitches):
            if pitches[start - 1] == pitches[end] and pitches[end] >= 0:
                pitches[start:end] = pitches[end]
    notes = []
    for start, end in _runs(pitches):
        if pitches[start] < 0:
            continue
        begin = max(0.0, float(times[start]) - step / 2)
        stop = min(duration, float(times[end - 1]) + step / 2)
        if stop - begin < minimum_duration:
            continue
        boundaries = [begin]
        for onset in onset_times:
            if onset - boundaries[-1] >= minimum_duration and stop - onset >= minimum_duration:
                if begin < onset < stop:
                    boundaries.append(float(onset))
        boundaries.append(stop)
        for left, right in zip(boundaries, boundaries[1:], strict=False):
            mask = (times >= left) & (times < right) & valid
            score = float(np.mean(scores[mask])) if mask.any() else 0.0
            notes.append(
                Note(
                    id=f"n{len(notes):05d}",
                    start=round(left, 6),
                    end=round(right, 6),
                    pitch=int(np.clip(pitches[start], 0, 127)),
                    score=float(np.clip(score, 0, 1)),
                )
            )
    return notes


def stable_notes_from_contour(
    times, frequencies, scores, duration, *, bridge_seconds=0.1, share_gaps=True
) -> list[Note]:
    """Decode sustained pitch states; legacy gap behavior remains the default."""
    if not len(times):
        return []
    valid = np.isfinite(frequencies) & (frequencies > 0)
    if not valid.any():
        return []
    midi = np.full(len(times), 0.0)
    midi[valid] = 69 + 12 * np.log2(frequencies[valid] / 440)
    low, high = max(1, int(midi[valid].min()) - 2), min(127, int(np.ceil(midi[valid].max())) + 2)
    states = np.r_[-1, np.arange(low, high + 1)]
    emissions = -np.minimum((midi[:, None] - states[None, :]) ** 2 * 2, 16)
    emissions[:, 0] = -3
    emissions[~valid, :] = -5
    emissions[~valid, 0] = 0
    transition = np.full((len(states), len(states)), -2.5)
    transition[0, :] = transition[:, 0] = -1.5
    np.fill_diagonal(transition, 0)
    previous = np.zeros((len(times), len(states)), dtype=np.int16)
    cost = emissions[0].copy()
    for index in range(1, len(times)):
        paths = cost[:, None] + transition
        previous[index] = paths.argmax(axis=0)
        cost = paths.max(axis=0) + emissions[index]
    path = np.empty(len(times), dtype=int)
    path[-1] = int(cost.argmax())
    for index in range(len(times) - 1, 0, -1):
        path[index - 1] = previous[index, path[index]]
    pitches = states[path]
    step = float(np.median(np.diff(times))) if len(times) > 1 else HOP / RATE
    for start, end in list(_runs(pitches)):
        if (end - start) * step <= bridge_seconds and start and end < len(pitches):
            if pitches[start - 1] == pitches[end] and pitches[end] >= 0:
                pitches[start:end] = pitches[end]
    notes = []
    for start, end in _runs(pitches):
        if pitches[start] < 0 or (end - start) * step < 0.08:
            continue
        notes.append(
            Note(
                id=f"n{len(notes):05d}",
                pitch=int(pitches[start]),
                start=max(0, float(times[start]) - step / 2),
                end=min(duration, float(times[end - 1]) + step / 2),
                score=float(np.clip(np.mean(scores[start:end]), 0, 1)),
            )
        )
    for left, right in zip(notes, notes[1:] if share_gaps else [], strict=False):
        gap = right.start - left.end
        if 0 < gap <= 0.25:
            boundary = (left.end + right.start) / 2
            left.end = right.start = round(boundary, 6)
    return notes


def extract_melody(source: Path, output: Path, config: dict) -> Melody:
    import librosa

    audio = load_mono(source, RATE)
    duration = len(audio) / RATE
    all_times, all_pitch, all_scores = [], [], []
    block = 20 * RATE
    padding = RATE // 2
    backend = config["pitch_backend"]
    for offset in range(0, len(audio), block):
        core_end = min(len(audio), offset + block)
        left, right = max(0, offset - padding), min(len(audio), core_end + padding)
        chunk = audio[left:right]
        if np.max(np.abs(chunk), initial=0) < 1e-5:
            count = len(chunk) // HOP + 1
            pitch, score = np.full(count, np.nan), np.zeros(count)
        elif backend == "crepe":
            import torch
            import torchcrepe

            with torch.inference_mode():
                pitch_t, score_t = torchcrepe.predict(
                    torch.from_numpy(chunk)[None],
                    RATE,
                    HOP,
                    65.4,
                    1046.5,
                    model="full",
                    batch_size=256,
                    device=config["device"],
                    return_periodicity=True,
                )
            pitch, score = pitch_t[0].cpu().numpy(), score_t[0].cpu().numpy()
        else:
            pitch, _, score = librosa.pyin(
                chunk,
                fmin=65.4,
                fmax=1046.5,
                sr=RATE,
                frame_length=1024,
                hop_length=HOP,
                fill_na=np.nan,
            )
        rms = librosa.feature.rms(y=chunk, frame_length=1024, hop_length=HOP)[0]
        count = min(len(pitch), len(rms))
        pitch, score = pitch[:count].copy(), np.nan_to_num(score[:count])
        floor = max(1e-5, float(np.max(rms, initial=0)) * 0.008)
        pitch[(score < config["pitch_threshold"]) | (rms[:count] < floor)] = np.nan
        times = left / RATE + np.arange(count) * HOP / RATE
        keep = (times >= offset / RATE) & (times < core_end / RATE)
        all_times.append(times[keep])
        all_pitch.append(pitch[keep])
        all_scores.append(score[keep])
    times = np.concatenate(all_times)
    pitch = np.concatenate(all_pitch)
    score = np.concatenate(all_scores)
    if config.get("melody_decoder") in ("stable", "rest"):
        preserve = config.get("melody_decoder") == "rest"
        notes = stable_notes_from_contour(
            times,
            pitch,
            score,
            duration,
            bridge_seconds=0 if preserve else 0.1,
            share_gaps=not preserve,
        )
    else:
        onsets = librosa.onset.onset_detect(y=audio, sr=RATE, hop_length=HOP, units="time")
        notes = notes_from_contour(times, pitch, score, duration, onset_times=onsets)
    write_json(
        output / "analysis/pitch.json",
        {
            "timebase": "seconds_from_decoded_audio_start",
            "hop_seconds": HOP / RATE,
            "times": np.round(times, 6).tolist(),
            "frequency_hz": [round(float(p), 3) if np.isfinite(p) else None for p in pitch],
            "periodicity": np.round(score, 4).tolist(),
        },
    )
    return Melody(
        backend=backend + "/" + config.get("melody_decoder", "classic"),
        notes=notes,
        warnings=[
            "Monophonic vocal estimate; harmony, vibrato and repeated notes may need editing. "
            "Scores are pitch periodicity, not calibrated note accuracy."
        ],
    )
