from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from .io import read_json, sha256
from .schema import Project


def validate_project(path: Path) -> dict:
    path = path.resolve()
    if path.is_dir():
        path = path / "project.json"
    project = Project.model_validate(read_json(path))
    root = path.parent
    state = read_json(root / "run.json")
    if state.get("status") != "complete":
        raise ValueError("Latest run is incomplete; project.json may belong to an earlier run")
    if state.get("source_sha256") != project.audio.source_sha256:
        raise ValueError("Project source differs from latest run")
    for relative in project.assets.values():
        asset = (root / relative).resolve()
        if not asset.is_relative_to(root) or not asset.is_file():
            raise ValueError(f"Missing or invalid asset: {relative}")
    for kind in ("source", "vocals", "instrumental"):
        info = sf.info(root / project.assets[kind])
        if (info.frames, info.samplerate, info.channels) != (
            project.audio.samples,
            project.audio.sample_rate,
            project.audio.channels,
        ):
            raise ValueError(f"Audio timeline mismatch: {kind}")
    for stage in state["stages"].values():
        for relative, digest in stage["artifacts"].items():
            asset = (root / relative).resolve()
            if not asset.is_relative_to(root) or sha256(asset) != digest:
                raise ValueError(f"Cached artifact changed: {relative}")
    contour = read_json(root / project.assets["pitch"])
    times = contour["times"]
    if len(times) != len(contour["frequency_hz"]) or len(times) != len(contour["periodicity"]):
        raise ValueError("Pitch contour columns have different lengths")
    if any(not np.isfinite(t) or t < 0 or t >= project.audio.duration for t in times):
        raise ValueError("Pitch contour exceeds the audio timeline")
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Pitch contour time is not strictly increasing")
    midi = mido.MidiFile(root / project.assets["midi"], charset="utf-8")
    actual, active, time = [], {}, 0.0
    for message in midi:
        time += message.time
        if message.type == "note_on" and message.velocity > 0:
            if message.note in active:
                raise ValueError("Overlapping MIDI notes have the same pitch")
            active[message.note] = time
        elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
            if message.note not in active:
                raise ValueError("MIDI note-off has no note-on")
            actual.append((active.pop(message.note), time, message.note))
    if active:
        raise ValueError("MIDI contains unterminated notes")
    expected = sorted((n.start, n.end, n.pitch) for n in project.melody.notes)
    actual.sort()
    if len(actual) != len(expected):
        raise ValueError("MIDI note count differs from project")
    for (start, end, pitch), (wanted_start, wanted_end, wanted_pitch) in zip(
        actual, expected, strict=False
    ):
        if pitch != wanted_pitch or max(abs(start - wanted_start), abs(end - wanted_end)) > 0.01:
            raise ValueError("MIDI note timing or pitch differs from project")
    return {
        "valid": True,
        "duration": project.audio.duration,
        "lyrics": len(project.lyrics.segments),
        "notes": len(actual),
        "chords": len(project.harmony.chords),
        "beats": len(project.rhythm.beats),
        "assets": len(project.assets),
    }
