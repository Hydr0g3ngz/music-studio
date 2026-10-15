"""Verify the selected rest decoder on the frozen GTS regression and MIDI round trips."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from benchmark_lib import load_reference, score_case  # noqa: E402
from evaluate_melody_next import midi_roundtrip  # noqa: E402

from music_studio.backends.melody import stable_notes_from_contour  # noqa: E402
from music_studio.export import write_midi  # noqa: E402
from music_studio.io import read_json, sha256, write_json  # noqa: E402
from music_studio.schema import Lyrics, Melody, Rhythm  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--cached", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new directory; previous results are retained")
    args.output.mkdir(parents=True)
    manifest = ROOT / "benchmarks/suite-v1.json"
    rows = []
    for case in read_json(manifest)["cases"]:
        if "notes" not in case.get("tasks", []):
            continue
        directory = args.output / case["id"]
        directory.mkdir()
        baseline = Melody.model_validate(
            read_json(args.cached / case["id"] / "analysis/melody.json")
        )
        reference = load_reference(case, args.data)
        contour_path = args.cached / case["id"] / "analysis/pitch.json"
        contour = read_json(contour_path)
        candidate = Melody(
            backend="crepe/rest",
            notes=stable_notes_from_contour(
                np.asarray(contour["times"]),
                np.asarray(contour["frequency_hz"], dtype=float),
                np.asarray(contour["periodicity"]),
                reference["duration"],
                bridge_seconds=0,
                share_gaps=False,
            ),
        )
        scores = {}
        for name, melody in (("baseline", baseline), ("candidate", candidate)):
            scores[name] = score_case(case, reference, {"melody": melody.model_dump()}, directory)
        write_json(directory / "melody.json", candidate.model_dump())
        write_midi(
            directory / "melody.mid",
            candidate,
            Rhythm(backend="natural", bpm=120, beats=[]),
            Lyrics(language=None, timing_method="none", segments=[]),
        )
        rows.append(
            {
                "id": case["id"],
                "language": case["language"],
                "metrics": scores,
                "contour_sha256": sha256(contour_path),
                "midi_max_error_seconds": midi_roundtrip(directory / "melody.mid", candidate),
            }
        )
    groups = {
        language: {
            key: {
                method: float(
                    np.mean(
                        [
                            row["metrics"][method][key]["f1"]
                            for row in rows
                            if row["language"] == language
                        ]
                    )
                )
                for method in ("baseline", "candidate")
            }
            for key in ("note_onset_pitch", "note_onset_offset_pitch")
        }
        for language in sorted({row["language"] for row in rows})
    }
    report = {
        "suite_sha256": sha256(manifest),
        "decoder_sha256": sha256(ROOT / "src/music_studio/backends/melody.py"),
        "cases": rows,
        "groups": groups,
    }
    write_json(args.output / "report.json", report)
    print(json.dumps(groups), flush=True)


if __name__ == "__main__":
    main()
