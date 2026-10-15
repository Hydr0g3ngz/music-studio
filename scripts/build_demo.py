"""Build the credited, precomputed preview from an actual completed Fishin' analysis.

Only use the licensed example named below. This is a presentation artifact, never
a benchmark input or a reference annotation. Neural inference is not run here.
"""

import argparse
from pathlib import Path

import soundfile as sf

from music_studio.export import export_project, link_words
from music_studio.io import read_json, sha256, write_json
from music_studio.schema import Project


def build(source: Path, target: Path, seconds=45.0):
    raw = read_json(source / "project.json")
    if "fishin" not in raw["audio"]["source_name"].lower():
        raise ValueError("Only the credited Let's Go Fishin' example may be bundled")
    project = Project.model_validate(raw).model_copy(deep=True)
    target.mkdir(parents=True, exist_ok=True)
    duration = min(seconds, project.audio.duration)
    for name in ("source", "vocals", "instrumental"):
        audio, rate = sf.read(source / project.assets[name], dtype="float32", always_2d=True)
        audio = audio[: round(duration * rate)]
        relative = f"audio/{name}.ogg"
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        # Bound encoder writes: large single Vorbis writes can abort libsndfile on Windows.
        with sf.SoundFile(
            target / relative, "w", samplerate=rate, channels=audio.shape[1],
            format="OGG", subtype="VORBIS",
        ) as output:
            for left in range(0, len(audio), 4096):
                output.write(audio[left:left + 4096])
        project.assets[name] = relative
    project.audio.source_name = "Lets-Go-Fishin-preview.ogg"
    project.audio.samples = len(audio)
    project.audio.duration = len(audio) / rate
    project.audio.source_sha256 = sha256(target / project.assets["source"])
    # Keep complete lyric phrases only; do not pretend a cropped phrase was fully sung.
    project.lyrics.segments = [line for line in project.lyrics.segments if line.end <= duration]
    project.melody.notes = [note for note in project.melody.notes if note.start < duration]
    for note in project.melody.notes:
        note.end = min(note.end, duration)
    project.harmony.chords = [c for c in project.harmony.chords if c.start < duration]
    for chord in project.harmony.chords:
        chord.end = min(chord.end, duration)
    project.rhythm.beats = [time for time in project.rhythm.beats if time < duration]
    project.rhythm.downbeats = [time for time in project.rhythm.downbeats if time < duration]
    link_words(project.melody, project.lyrics)
    pitch = read_json(source / project.assets["pitch"])
    count = sum(time < duration for time in pitch["times"])
    for key, value in pitch.items():
        if isinstance(value, list):
            pitch[key] = value[:count]
    write_json(target / project.assets["pitch"], pitch)
    project.settings["model_dir"] = ".cache/models"
    project.settings["lyrics_python"] = None
    project.settings["precomputed_demo"] = True
    project.stages = {}
    project.warnings = [
        "Precomputed, cropped demo; machine estimates, not ground truth. "
        "Audio previews are lossy Ogg Vorbis derivatives of the original and separated stems. "
        "Do not use these compressed assets for benchmark reproduction."
    ]
    project = Project.model_validate(project.model_dump())
    export_project(project, target)
    write_json(target / "project.json", project.model_dump())
    attribution = {
        "title": "Let's Go Fishin'", "artist": "Karissa Hobbs", "license": "CC BY 3.0",
        "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "source_url": "https://librosa.org/data/audio/Karissa_Hobbs_-_Lets_Go_Fishin.txt",
        "original_url": "https://freemusicarchive.org/music/Karissa_Hobbs/Age_of_Flowers/09_Lets_Go_Fishin",
    }
    write_json(target / "manifest.json", {
        "schema": "music-studio-demo/1", "attribution": attribution,
        "changes": "First 45 seconds; Demucs separation; Ogg previews; estimated annotations.",
        "original_project_sha256": sha256(source / "project.json"),
        "original_decoded_audio_sha256": raw["audio"]["source_sha256"],
        "files": {p.relative_to(target).as_posix(): sha256(p)
                  for p in sorted(target.rglob("*")) if p.is_file() and p.name != "manifest.json"},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("src/music_studio/ui/demo"))
    args = parser.parse_args()
    build(args.source, args.output)
    print(f"Demo written to {args.output}")
