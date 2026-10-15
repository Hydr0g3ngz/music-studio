"""Freeze the 17 manually aligned MIR-1K recordings; no new annotations or model selection.

The original audio endpoint is unavailable. Individual, version-pinned Kaggle mirror
files are used; upstream annotation and extracted WAV hashes are recorded separately.
Audio and annotation text stay in the ignored benchmark data directory.
"""

import argparse
import hashlib
import io
import json
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import soundfile as sf

from music_studio.io import sha256, write_json

REVISION = "1c39cd0369ce7dc55fa45277b59215b333d3a817"
ANNOTATIONS = (
    f"https://raw.githubusercontent.com/navi0105/LyricAlignment/{REVISION}/"
    "dataset_preprocessing/MIR1k_partial_align.json"
)
MIRROR = "https://www.kaggle.com/api/v1/datasets/download/datongmuyuyi/mir1k/"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MusicStudio-benchmark/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def groups(records):
    """Join recordings with a shared singer or substantially overlapping lyrics."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i

    for i, left in enumerate(records):
        for j, right in enumerate(records[:i]):
            same_singer = (
                left["song_id"].split("_")[0].casefold()
                == right["song_id"].split("_")[0].casefold()
            )
            match = SequenceMatcher(None, left["lyric"], right["lyric"], autojunk=False)
            same_song = match.ratio() >= 0.45 or match.find_longest_match().size >= 20
            if same_singer or same_song:
                parent[find(i)] = find(j)
    clusters = {}
    for i, record in enumerate(records):
        clusters.setdefault(find(i), []).append(record["song_id"])
    # Split decided from IDs before any new-model inference. Whole clusters stay together.
    return sorted(
        clusters.values(),
        key=lambda ids: hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/data"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/suite-v2-mir1k.json"))
    args = parser.parse_args()
    root = args.data / "mir1k"
    root.mkdir(parents=True, exist_ok=True)
    annotation = root / "annotations.json"
    data = fetch(ANNOTATIONS)
    annotation.write_bytes(data)
    records = sorted((x for x in json.loads(data) if "on_offset" in x), key=lambda x: x["song_id"])
    if len(records) != 17:
        raise ValueError("The pinned human-aligned subset must contain 17 recordings")
    clusters = groups(records)
    development = {name for cluster in clusters[::2] for name in cluster}

    def prepare(record):
        name = record["song_id"]
        member = f"MIR-1K/UndividedWavfile/{name}"
        url = MIRROR + urllib.parse.quote(member, safe="") + "?datasetVersionNumber=1"
        original = root / "raw" / name
        original.parent.mkdir(exist_ok=True)
        if not original.exists():
            with zipfile.ZipFile(io.BytesIO(fetch(url))) as archive:
                choices = [n for n in archive.namelist() if Path(n).name == name]
                if len(choices) != 1:
                    raise ValueError(f"Unexpected mirror archive: {name}")
                original.write_bytes(archive.read(choices[0]))
        audio, rate = sf.read(original, dtype="float32", always_2d=True)
        if audio.shape[1] != 2 or len(record["lyric"]) != len(record["on_offset"]):
            raise ValueError(f"Unexpected recording/annotation format: {name}")
        if max(b for _, b in record["on_offset"]) > len(audio) / rate + 0.05:
            raise ValueError(f"Recording does not match annotation duration: {name}")
        mixture = root / "mix" / name
        mixture.parent.mkdir(exist_ok=True)
        sf.write(mixture, np.mean(audio, axis=1), rate, subtype="FLOAT")
        assets = [
            {
                "path": str(original.relative_to(args.data)).replace("\\", "/"),
                "url": url,
                "archive_format": "zip-download",
                "archive_member_basename": name,
                "bytes": original.stat().st_size,
                "sha256": sha256(original),
            },
            {
                "path": str(mixture.relative_to(args.data)).replace("\\", "/"),
                "derived_from": str(original.relative_to(args.data)).replace("\\", "/"),
                "transform": "stereo-channel-mean-float32-wav-v1",
                "bytes": mixture.stat().st_size,
                "sha256": sha256(mixture),
            },
        ]
        identifier = "mir1k-" + original.stem.lower().replace("_", "-")
        case = {
            "id": identifier,
            "dataset": "mir1k",
            "domain": "lyrics_mandarin_karaoke_mix",
            "language": "zh",
            "audio": assets[1]["path"],
            "smoke": False,
            "split": "development" if name in development else "confirmation",
            "group": next(i for i, cluster in enumerate(clusters) if name in cluster),
            "singer": name.split("_")[0].lower(),
            "reference": {
                "format": "mir1k-partial-align",
                "path": "mir1k/annotations.json",
                "key": name,
            },
            "annotation": "Human verified text and character onsets/offsets from ASRU 2023 authors",
            "audio_license": (
                "Original MIR-1K source terms; mirror metadata says CC BY 4.0; "
                "do not redistribute audio"
            ),
        }
        print(f"Verified {identifier}: {len(audio) / rate:.1f}s, {case['split']}", flush=True)
        return case, assets

    with ThreadPoolExecutor(max_workers=4) as pool:
        prepared = list(pool.map(prepare, records))
    suite = {
        "schema_version": "1.0",
        "name": "music-studio-mir1k-confirmation-v2",
        "created": "2026-10-15",
        "purpose": (
            "New local development/confirmation split, not a claim of model-training exclusion"
        ),
        "selection": {
            "rule": (
                "All 17 human-aligned recordings; singer/lyric-overlap clusters alternate "
                "by SHA-256 order before inference"
            ),
            "groups": clusters,
            "limitations": [
                "Amateur karaoke recordings, not commercial master recordings",
                "Qwen/Whisper pretraining membership unknown",
                "Only 17 recordings; no new manual annotations",
            ],
        },
        "datasets": {
            "mir1k": {
                "url": "https://github.com/navi0105/LyricAlignment",
                "revision": REVISION,
                "audio_mirror": "https://www.kaggle.com/datasets/datongmuyuyi/mir1k/versions/1",
                "annotation_license": (
                    "No explicit repository license; metadata and scores only are published"
                ),
                "license": (
                    "Per upstream sources; audio and annotation contents are not redistributed"
                ),
            }
        },
        "assets": [
            {
                "path": "mir1k/annotations.json",
                "url": ANNOTATIONS,
                "bytes": len(data),
                "sha256": sha256(annotation),
            }
        ]
        + [asset for _, assets in prepared for asset in assets],
        "cases": [case for case, _ in prepared],
    }
    write_json(args.output, suite)
    print(
        f"Frozen {len(records)} recordings: {len(development)} development, "
        f"{17 - len(development)} confirmation; {sha256(args.output)}"
    )


if __name__ == "__main__":
    main()
