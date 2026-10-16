"""Rebuild the small, licensed factory library from pinned public sources.

Run manually with the development environment. Never runs during app startup.
Original downloads stay in .artifacts; only trimmed lossless samples and derived
two-bar drum templates are packaged. No third-party Python code is executed.
"""

import concurrent.futures
import csv
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".artifacts/library-research"
OUT = ROOT / "src/music_studio/data/creation"
REVISION = "c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e"
VCSL = f"https://raw.githubusercontent.com/sgossner/VCSL/{REVISION}/"
GROOVE_URL = "https://storage.googleapis.com/magentadata/datasets/groove/groove-v1.0.0-midionly.zip"
GROOVE_SHA = "651cbc524ffb891be1a3e46d89dc82a1cecb09a57c748c7b45b844c4841dcc1e"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def download(url, name):
    path = CACHE / name
    if path.exists():
        return path.read_bytes()
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Music-Studio-library/1"})
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(32 * 1024 * 1024)
            path.write_bytes(data)
            return data
        except OSError:
            if attempt == 3:
                raise
            time.sleep(attempt + 1)


def sources():
    selected = []
    for pitch, label in [
        (36, "C1"),
        (42, "F#1"),
        (48, "C2"),
        (54, "F#2"),
        (60, "C3"),
        (66, "F#3"),
        (72, "C4"),
        (78, "F#4"),
        (84, "C5"),
    ]:
        selected.append(
            (
                f"piano-{pitch}",
                "vcsl-piano",
                pitch,
                [],
                "Chordophones/Zithers/Grand Piano, Kawai/Sustains/"
                f"GPiano_sus_{label}_v3_rr1_Player.wav",
                6.0,
            )
        )
    for pitch, label in [(48, "C2"), (59, "B2"), (72, "C4"), (83, "B4"), (96, "C6")]:
        selected.append(
            (
                f"marimba-{pitch}",
                "vcsl-marimba",
                pitch,
                [],
                f"Idiophones/Struck Idiophones/Marimba/Marimba_hit_Outrigger_{label}_med_01.wav",
                4.0,
            )
        )
    for identity, pitch, aliases, source, length in [
        (
            "kick",
            36,
            [35, 36],
            "Membranophones/Struck Membranophones/Bass Drum 1/BDrumNew_hit_v5_rr1_Sum.wav",
            2,
        ),
        (
            "snare",
            38,
            [38, 40],
            "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitSN_v5_rr1_Mid.wav",
            2,
        ),
        (
            "rim",
            37,
            [37],
            "Membranophones/Struck Membranophones/Snare Drum, Modern 1/Snare2_HitNS_v4_rr1_Mid.wav",
            1,
        ),
        (
            "closed-hat",
            42,
            [22, 42, 44],
            "Idiophones/Struck Idiophones/Hi-Hat Cymbal/HiHat_HitC_v3_rr1_Mid.wav",
            1,
        ),
        (
            "open-hat",
            46,
            [26, 46],
            "Idiophones/Struck Idiophones/Hi-Hat Cymbal/HiHat_HitLoose_rr1_Mid.wav",
            3,
        ),
        (
            "tom",
            47,
            [41, 43, 45, 47, 48, 50],
            "Membranophones/Struck Membranophones/Tom 1/Stick/TomH_HitS_v3_rr1_Mid.wav",
            2,
        ),
        (
            "crash",
            49,
            [49, 52, 55, 57],
            "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_f1.wav",
            4,
        ),
        (
            "ride",
            51,
            [51, 53, 59],
            "Idiophones/Struck Idiophones/Suspended Cymbal 1/susCymb1_hit_bell_mf1.wav",
            4,
        ),
        ("clap", 39, [39], "Idiophones/Struck Idiophones/Claps/Clap_rr1.wav", 1),
    ]:
        selected.append((identity, "vcsl-drums", pitch, aliases, source, length))
    return selected


def prepare_sample(item):
    identity, instrument, pitch, aliases, source, limit = item
    url = VCSL + urllib.parse.quote(source, safe="/")
    raw = download(url, f"vcsl-{identity}.wav")
    data, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    if rate != 44100:
        import math

        from scipy.signal import resample_poly

        divisor = math.gcd(rate, 44100)
        data = resample_poly(data, 44100 // divisor, rate // divisor).astype("float32")
    data = data[: round(limit * 44100), :2]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    # Remove leading recording silence, preserving 2 ms before the measured onset.
    active = np.flatnonzero(np.max(np.abs(data), axis=1) > 0.002)
    trim = max(0, int(active[0]) - 88) if len(active) else 0
    data = data[trim:]
    peak = np.max(np.abs(data), initial=0)
    if not np.isfinite(data).all() or peak < 0.001:
        raise ValueError(f"Invalid sample: {source}")
    data *= 0.55 / peak
    fade = min(882, len(data))
    data[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    path = OUT / f"{identity}.flac"
    sf.write(path, data, 44100, subtype="PCM_16")
    print(f"Sample {identity}: {len(data) / 44100:.2f}s", flush=True)
    return {
        "id": identity,
        "instrument": instrument,
        "root": pitch,
        "keys": aliases,
        "file": path.name,
        "sha256": sha(path.read_bytes()),
        "frames": len(data),
        "source_url": url,
        "source_sha256": sha(raw),
        "source_path": source,
        "trim_start_frames": trim,
    }


def patterns():
    raw = download(GROOVE_URL, "groove-midi.zip")
    if sha(raw) != GROOVE_SHA:
        raise ValueError("Groove download checksum mismatch")
    result = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("groove/info.csv").decode("utf8"))))
        for style in ["pop", "rock", "funk", "hiphop", "soul", "jazz", "latin", "afrobeat"]:
            options = [
                r
                for r in rows
                if r["style"].split("/")[0] == style
                and r["beat_type"] == "beat"
                and r["time_signature"] == "4-4"
                and r["split"] == "train"
                and float(r["duration"]) > 12
            ]
            row = sorted(options, key=lambda r: r["id"])[0]
            source = archive.read("groove/" + row["midi_filename"])
            midi = mido.MidiFile(file=io.BytesIO(source))
            tick, notes = 0, []
            for message in mido.merge_tracks(midi.tracks):
                tick += message.time
                beat = tick / midi.ticks_per_beat
                # One bar into each performance, keep two bars and microtiming.
                if message.type == "note_on" and message.velocity and 4 <= beat < 12:
                    pitch = {22: 42, 26: 46}.get(message.note, message.note)
                    notes.append(
                        {
                            "pitch": pitch,
                            "start": round(beat - 4, 7),
                            "length": 0.12,
                            "velocity": message.velocity,
                        }
                    )
            if not notes or len(notes) > 512:
                raise ValueError(f"Invalid groove selection {row['id']}")
            result.append(
                {
                    "id": f"groove-{style}",
                    "title": style.title() + " pocket",
                    "style": style,
                    "bpm": int(row["bpm"]),
                    "beats": 8,
                    "notes": notes,
                    "origin": {
                        "title": "Groove MIDI Dataset: " + row["midi_filename"],
                        "author": (
                            "Jon Gillick, Adam Roberts, Jesse Engel, Douglas Eck, "
                            "David Bamman; Google LLC; " + row["drummer"]
                        ),
                        "license": "CC-BY-4.0",
                        "source_url": "https://magenta.withgoogle.com/datasets/groove",
                        "sha256": sha(source),
                        "details": (
                            "Two-bar excerpt at beats 4–12; original microtiming/velocity; "
                            "drum aliases 22→42, 26→46; fixed 0.12-beat note gates. "
                            "Source split: train."
                        ),
                    },
                }
            )
    return result


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        samples = list(pool.map(prepare_sample, sources()))
    license_text = download(VCSL + "LICENSE", "vcsl-license.txt")
    (OUT / "LICENSE-VCSL.txt").write_bytes(license_text)
    manifest = {
        "version": 1,
        "rate": 44100,
        "vcsl_revision": REVISION,
        "groove_archive_sha256": GROOVE_SHA,
        "instruments": [
            {
                "id": "vcsl-piano",
                "title": ["采样三角钢琴", "Sampled grand piano"],
                "drum": False,
                "program": 0,
            },
            {
                "id": "vcsl-marimba",
                "title": ["采样马林巴", "Sampled marimba"],
                "drum": False,
                "program": 12,
            },
            {
                "id": "vcsl-drums",
                "title": ["原声采样鼓组", "Acoustic sample kit"],
                "drum": True,
                "program": 0,
            },
        ],
        "origin": {
            "title": "Versilian Community Sample Library",
            "author": "Versilian Studios and VCSL contributors",
            "license": "CC0-1.0",
            "source_url": "https://github.com/sgossner/VCSL",
            "details": (
                "Curated single-layer starter pack; onset trim, peak normalization, "
                "duration trim/fade, stereo conversion, lossless FLAC. "
                "No sample loops or SFZ import."
            ),
        },
        "samples": samples,
        "patterns": patterns(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(f"Built {len(samples)} samples and {len(manifest['patterns'])} grooves in {OUT}")


if __name__ == "__main__":
    main()
