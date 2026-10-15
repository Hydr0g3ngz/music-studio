"""Compare gap-preserving decoding without rerunning or tuning the pitch network.

The singer split is fixed before decoding and used only for this follow-up.
Vocadito was already inspected in a prior model comparison: this is not a new blind test.
No held-out note labels are read by the development command.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate_melody_next import midi_roundtrip  # noqa: E402
from evaluate_vocadito import score  # noqa: E402

from music_studio.backends.melody import stable_notes_from_contour  # noqa: E402
from music_studio.export import write_midi  # noqa: E402
from music_studio.io import read_json, sha256, write_json  # noqa: E402
from music_studio.schema import Lyrics, Melody, Rhythm  # noqa: E402


def split(suite):
    singers = sorted(
        {c["singer"] for c in suite["cases"]},
        key=lambda s: hashlib.sha256(("boundary-v1:" + s).encode()).hexdigest(),
    )
    development = set(singers[: len(singers) // 2])
    return {
        c["id"]: "development" if c["singer"] in development else "heldout" for c in suite["cases"]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--cached", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--partition", choices=["development", "heldout"], default="development")
    parser.add_argument("--bridges", type=float, nargs="+", default=[0, 0.02, 0.04])
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output path; previous results are retained")
    if args.partition == "heldout" and len(args.bridges) != 1:
        parser.error("Select one candidate on development before opening held-out labels")
    manifest = ROOT / "benchmarks/vocadito-v1.json"
    suite = read_json(manifest)
    assignment = split(suite)
    frozen = read_json(ROOT / "benchmarks/melody-boundaries-v1.json")
    if assignment != frozen["split"] or sha256(manifest) != frozen["suite_sha256"]:
        parser.error("Frozen singer split or source suite changed; create a new protocol")
    if args.partition == "heldout" and args.bridges != [frozen["selected"]["bridge_seconds"]]:
        parser.error("Held-out evaluation requires the previously selected candidate")
    engine = args.output.with_suffix("")
    engine.mkdir(parents=True, exist_ok=False)
    import shutil

    for file in (Path(__file__), ROOT / "src/music_studio/backends/melody.py"):
        shutil.copyfile(file, engine / file.name)
    report = {
        "protocol": "singer-separated follow-up; all clips previously used for model comparison",
        "suite_sha256": sha256(manifest),
        "decoder_sha256": sha256(ROOT / "src/music_studio/backends/melody.py"),
        "split": assignment,
        "partition": args.partition,
        "candidates": {},
    }
    selected = [c for c in suite["cases"] if assignment[c["id"]] == args.partition]
    for bridge in args.bridges:
        rows = []
        for case in selected:
            folder = args.cached / case["id"]
            contour = read_json(folder / "analysis/pitch.json")
            times = np.asarray(contour["times"])
            f0 = np.asarray(contour["frequency_hz"], dtype=float)
            confidence = np.asarray(contour["periodicity"])
            baseline = Melody.model_validate(read_json(folder / "melody.json"))
            for role, relative in case["files"].items():
                if sha256(args.data / relative) != case["sha256"][role]:
                    raise ValueError("Frozen data hash mismatch: " + case["id"] + "/" + role)
            duration = sf.info(args.data / case["files"]["audio"]).duration
            notes = stable_notes_from_contour(
                times, f0, confidence, duration, bridge_seconds=bridge, share_gaps=False
            )
            melody = Melody(backend=f"crepe/rest-{bridge}", notes=notes)
            midi_path = engine / f"{case['id']}-{bridge}.mid"
            write_midi(
                midi_path,
                melody,
                Rhythm(backend="natural", bpm=120, beats=[]),
                Lyrics(language=None, timing_method="none", segments=[]),
            )
            rows.append(
                {
                    "id": case["id"],
                    "singer": case["singer"],
                    "baseline": score(args.data, case, baseline, times, f0),
                    "candidate": score(args.data, case, melody, times, f0),
                    "counts": {"baseline": len(baseline.notes), "candidate": len(notes)},
                    "contour_sha256": sha256(folder / "analysis/pitch.json"),
                    "midi_max_error_seconds": midi_roundtrip(midi_path, melody),
                }
            )
        macro = {
            annotator: {
                key: {
                    method: float(np.mean([r[method][annotator][key]["f1"] for r in rows]))
                    for method in ("baseline", "candidate")
                }
                for key in ("onset_pitch", "onset_offset_pitch")
            }
            for annotator in ("A1", "A2")
        }
        report["candidates"][str(bridge)] = {"macro": macro, "cases": rows}
        print(json.dumps({"bridge": bridge, "clips": len(rows), "macro": macro}), flush=True)
    write_json(args.output, report)


if __name__ == "__main__":
    main()
