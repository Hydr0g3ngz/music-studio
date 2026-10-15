from pathlib import Path

import numpy as np

from ..audio import load_mono
from ..schema import Chord, Harmony, Rhythm

ROOTS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def chord_templates() -> tuple[np.ndarray, list[str]]:
    templates, names = [], []
    for root, name in enumerate(ROOTS):
        for third, suffix in ((4, ""), (3, "m")):
            vector = np.zeros(12)
            vector[[root, (root + third) % 12, (root + 7) % 12]] = [1, 0.9, 0.9]
            templates.append(vector / np.linalg.norm(vector))
            names.append(name + suffix)
    return np.asarray(templates), names


def classify_chroma(chroma: np.ndarray) -> tuple[str, float]:
    templates, names = chord_templates()
    norm = np.linalg.norm(chroma)
    if norm < 1e-8:
        return "N", 0.0
    scores = templates @ (chroma / norm)
    winner = int(scores.argmax())
    return names[winner], float(np.clip(scores[winner], 0, 1))


def estimate_harmony(source: Path, rhythm: Rhythm, config: dict | None = None) -> Harmony:
    import librosa

    rate, hop = 22050, 512
    audio = load_mono(source, rate)
    duration = len(audio) / rate
    if np.max(np.abs(audio), initial=0) < 1e-5:
        return Harmony(
            backend="chroma_template_viterbi",
            chords=[Chord(start=0, end=duration, label="N", score=0)],
        )
    harmonic = librosa.effects.harmonic(audio, margin=2.0)
    backend = (config or {}).get("harmony_backend", "stft")
    if backend == "cqt":
        tuning = librosa.estimate_tuning(y=harmonic, sr=rate)
        chroma = librosa.feature.chroma_cqt(y=harmonic, sr=rate, hop_length=hop, tuning=tuning)
        from scipy.ndimage import median_filter

        chroma = median_filter(chroma, size=(1, 5), mode="nearest")
    else:
        chroma = librosa.feature.chroma_stft(
            y=harmonic,
            sr=rate,
            n_fft=4096,
            hop_length=hop,
            tuning=0,
        )
    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=rate, hop_length=hop)
    interior = rhythm.beats if len(rhythm.beats) >= 2 else np.arange(0.5, duration, 0.5)
    boundaries = [0.0] + [float(t) for t in interior if 0.05 < t < duration - 0.05]
    boundaries.append(duration)
    templates, labels = chord_templates()
    emissions, raw_scores = [], []
    global_rms = float(np.sqrt(np.mean(audio**2)))
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        mask = (frame_times >= start) & (frame_times < end)
        feature = chroma[:, mask].mean(axis=1) if mask.any() else np.zeros(12)
        region = audio[int(start * rate) : max(int(end * rate), int(start * rate) + 1)]
        silent = np.sqrt(np.mean(region**2)) < max(1e-5, global_rms * 0.035)
        scores = templates @ (feature / max(np.linalg.norm(feature), 1e-8))
        # "N" means no confident major/minor estimate, including silence and percussion.
        emission = np.r_[scores, 0.57]
        if silent or np.linalg.norm(feature) < 1e-8:
            emission[:] = -10
            emission[-1] = 1
        emissions.append(emission)
        raw_scores.append(scores)
    emissions = np.asarray(emissions)
    costs = emissions[0].copy()
    previous = np.zeros_like(emissions, dtype=int)
    transition = np.full((25, 25), -0.12)
    np.fill_diagonal(transition, 0)
    for index in range(1, len(emissions)):
        candidates = costs[:, None] + transition
        previous[index] = candidates.argmax(axis=0)
        costs = candidates.max(axis=0) + emissions[index]
    states = [int(costs.argmax())]
    for index in range(len(emissions) - 1, 0, -1):
        states.append(int(previous[index, states[-1]]))
    states.reverse()
    labels.append("N")
    chords = []
    for index, state in enumerate(states):
        label = labels[state]
        score = float(np.clip(raw_scores[index][state], 0, 1)) if state < 24 else 0.0
        start, end = boundaries[index : index + 2]
        if chords and chords[-1].label == label:
            last = chords[-1]
            last.score = (last.score * (last.end - last.start) + score * (end - start)) / (
                end - last.start
            )
            last.end = end
        else:
            chords.append(Chord(start=start, end=end, label=label, score=score))
    return Harmony(
        backend=f"{backend}_template_viterbi",
        chords=chords,
        warnings=[
            "Major/minor chord approximation only; extensions and inversions are not estimated. "
            "Scores are template similarity, not calibrated accuracy."
        ],
    )
