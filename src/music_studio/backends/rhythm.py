from pathlib import Path

import numpy as np

from ..audio import load_mono
from ..schema import Rhythm


def estimate_rhythm(source: Path, config: dict | None = None) -> Rhythm:
    import librosa

    if config and config.get("rhythm_backend") == "beat_this":
        from beat_this.inference import Audio2Beats

        from ..beat_models import beat_checkpoint

        rate = 22050
        audio = load_mono(source, rate)
        if np.max(np.abs(audio), initial=0) < 1e-5:
            return Rhythm(backend="beat_this", beats=[], warnings=["No audible beat signal."])
        checkpoint = beat_checkpoint(config)
        tracker = Audio2Beats(checkpoint_path=str(checkpoint), device=config["device"], dbn=False)
        beats, downbeats = tracker(audio, rate)
        duration = len(audio) / rate
        beats = np.unique(beats[(beats >= 0) & (beats < duration)])
        downbeats = np.unique(downbeats[(downbeats >= 0) & (downbeats < duration)])
        bpm = float(60 / np.median(np.diff(beats))) if len(beats) >= 2 else None
        return Rhythm(
            backend=f"beat_this/{config['rhythm_checkpoint']}",
            beats=beats.tolist(),
            downbeats=downbeats.tolist(),
            bpm=bpm,
            warnings=["Automatic beats and downbeats; half/double tempo remains possible."],
        )

    percussive = bool(config and config.get("rhythm_backend") == "librosa_percussive")
    rate, hop = 22050, 256 if percussive else 512
    audio = load_mono(source, rate)
    if np.max(np.abs(audio), initial=0) < 1e-5:
        return Rhythm(backend="librosa", beats=[], warnings=["No audible beat signal."])
    transient_audio = librosa.effects.percussive(audio) if percussive else audio
    envelope = librosa.onset.onset_strength(y=transient_audio, sr=rate, hop_length=hop)
    tempo, frames = librosa.beat.beat_track(
        onset_envelope=envelope,
        sr=rate,
        hop_length=hop,
        trim=False,
    )
    beats = librosa.frames_to_time(frames, sr=rate, hop_length=hop)
    beats = beats[(beats >= 0) & (beats < len(audio) / rate)]
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    return Rhythm(
        backend="librosa_percussive" if percussive else "librosa",
        bpm=bpm if bpm > 0 and len(beats) >= 2 else None,
        beats=beats.tolist(),
        warnings=[
            "Beat positions are estimates; half/double tempo errors are possible. "
            "This backend does not estimate downbeats or time signatures."
        ],
    )
