"""Small offline factory sample library, with the same sampler semantics as Web Audio."""

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from ..io import sha256
from .service import StudioError

DIRECTORY = Path(__file__).resolve().parents[1] / "data/creation"
SAMPLED = ("vcsl-piano", "vcsl-marimba", "vcsl-drums")


@lru_cache(maxsize=1)
def manifest():
    return json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf8"))


def public():
    data = manifest()
    return {
        **data,
        "samples": [
            dict(s, url=f"/api/workstation/library/samples/{s['id']}") for s in data["samples"]
        ],
    }


def sample_path(identity):
    entry = next((s for s in manifest()["samples"] if s["id"] == identity), None)
    if not entry:
        raise StudioError("Sample does not exist", 404)
    path = DIRECTORY / entry["file"]
    if path.is_symlink() or path.resolve().parent != DIRECTORY.resolve():
        raise StudioError("Invalid factory sample")
    return path


@lru_cache(maxsize=32)
def sample(identity):
    entry = next(s for s in manifest()["samples"] if s["id"] == identity)
    path = sample_path(identity)
    if sha256(path) != entry["sha256"]:
        raise StudioError("Factory sample checksum mismatch; repair the installation")
    audio, rate = sf.read(path, dtype="float64", always_2d=True)
    if rate != 44100 or audio.shape[1] != 2 or not np.isfinite(audio).all():
        raise StudioError("Invalid factory sample format")
    return audio


@lru_cache(maxsize=384)
def choice(instrument, pitch):
    samples = [s for s in manifest()["samples"] if s["instrument"] == instrument]
    if instrument == "vcsl-drums":
        return next(
            (s for s in samples if pitch in s["keys"]),
            next(s for s in samples if s["id"] == "closed-hat"),
        )
    return min(samples, key=lambda s: (abs(s["root"] - pitch), s["root"]))


def note_audio(times, note, instrument, gate_seconds):
    entry = choice(instrument, note.pitch)
    output = np.zeros((len(times), 2))
    if entry is None:
        return output
    audio = sample(entry["id"])
    ratio = 1 if instrument == "vcsl-drums" else 2 ** ((note.pitch - entry["root"]) / 12)
    positions = times * ratio * 44100
    mask = (positions >= 0) & (positions < len(audio) - 1)
    if instrument != "vcsl-drums":
        mask &= times < gate_seconds
    x = positions[mask]
    low = x.astype(np.int64)
    blend = x - low
    data = audio[low] * (1 - blend[:, None]) + audio[low + 1] * blend[:, None]
    if instrument != "vcsl-drums":
        envelope = np.minimum(times[mask] / 0.003, 1) * np.minimum(
            (gate_seconds - times[mask]) / 0.04, 1
        )
        data *= np.maximum(envelope, 0)[:, None]
    output[mask] = data * (note.velocity / 127) * 0.55
    return output


def midi_audio(times, clip, bpm, instrument):
    """Render a bounded block from the clip's source time, including one-shot tails."""
    beat = 60 / bpm
    data = np.zeros((len(times), 2))
    if not len(times):
        return data
    hats = sorted({n.start for n in clip.notes if n.pitch in (22, 26, 42, 44, 46)})
    next_hat = dict(zip(hats, hats[1:], strict=False))
    for note in clip.notes:
        start = note.start * beat
        if start > times[-1]:
            continue
        gate = note.length * beat
        if instrument == "vcsl-drums":
            entry = choice(instrument, note.pitch)
            if entry is None:
                continue
            gate = entry["frames"] / 44100
            if note.pitch in (22, 26, 42, 44, 46):
                if note.start in next_hat:
                    gate = min(gate, (next_hat[note.start] - note.start) * beat)
        if start + gate <= times[0]:
            continue
        local = times - start
        active = (local >= 0) & (local < gate)
        if active.any():
            data[active] += note_audio(local[active], note, instrument, gate)
    return data
