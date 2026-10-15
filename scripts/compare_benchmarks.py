"""Paired, domain-specific comparisons. No combined accuracy score or missing-case wins."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from music_studio.io import read_json, write_json

METRICS = {
    "lyrics": ("lyrics", "rate", -1),
    "notes": ("note_onset_pitch", "f1", 1),
    "notes_with_offset": ("note_onset_offset_pitch", "f1", 1),
    "beats": ("beats", "F-measure", 1),
    "chord_root": ("chords", "root", 1),
    "chord_majmin": ("chords", "majmin", 1),
}


def compare(baseline: dict, candidate: dict, manifest: dict, *, allow_partial=False):
    if candidate.get("training_overlap"):
        raise ValueError("Known training overlap: this diagnostic cannot be used for promotion")
    if baseline.get("suite_sha256") != candidate.get("suite_sha256"):
        raise ValueError("Suite checksums differ")
    old = {r["id"]: r for r in baseline["cases"]}
    new = {r["id"]: r for r in candidate["cases"]}
    expected = {c["id"] for c in manifest["cases"]}
    missing = {
        "baseline": sorted(expected - old.keys()),
        "candidate": sorted(expected - new.keys()),
    }
    if not allow_partial and any(missing.values()):
        raise ValueError(f"Incomplete comparison: {missing}")
    grouped = defaultdict(list)
    cases = {c["id"]: c for c in manifest["cases"]}
    regressions = []
    for identifier in sorted(old.keys() & new.keys()):
        case = cases[identifier]
        for name, (section, key, direction) in METRICS.items():
            before = old[identifier]["metrics"].get(section, {})
            after = new[identifier]["metrics"].get(section, {})
            if key not in before or key not in after:
                continue
            row = {
                "id": identifier,
                "before": before[key],
                "after": after[key],
                "improvement": direction * (after[key] - before[key]),
                "cluster": case.get("voice", identifier),
            }
            if name == "lyrics":
                row.update(
                    before_errors=before["errors"],
                    after_errors=after["errors"],
                    tokens=before["reference_tokens"],
                )
                if before["reference_tokens"] != after["reference_tokens"]:
                    raise ValueError("Reference token counts differ")
            if name == "chord_majmin":
                if (
                    abs(
                        before["majmin_scored_reference_fraction"]
                        - after["majmin_scored_reference_fraction"]
                    )
                    > 1e-7
                ):
                    raise ValueError("Chord eligible duration changed")
            grouped[f"{case['dataset']}/{case['language'] or 'instrumental'}/{name}"].append(row)
            if row["improvement"] < -0.05:
                regressions.append({"metric": name, **row})
        for stem in ("vocals", "instrumental"):
            before = old[identifier]["metrics"].get("separation", {}).get(stem, {}).get("si_sdr_db")
            after = new[identifier]["metrics"].get("separation", {}).get(stem, {}).get("si_sdr_db")
            if before is not None and after is not None:
                grouped[f"{case['dataset']}/instrumental/{stem}_si_sdr_db"].append(
                    {
                        "id": identifier,
                        "before": before,
                        "after": after,
                        "improvement": after - before,
                        "cluster": identifier,
                    }
                )
    rng = np.random.default_rng(20261015)
    summary = {}
    for name, rows in grouped.items():
        is_text = name.endswith("/lyrics")
        clusters = sorted({r["cluster"] for r in rows})

        def value(selection, side, is_text=is_text):
            if is_text:
                return sum(r[f"{side}_errors"] for r in selection) / sum(
                    r["tokens"] for r in selection
                )
            return float(np.mean([r["before" if side == "before" else "after"] for r in selection]))

        direction = -1 if is_text else 1
        samples = []
        for _ in range(2000):
            selected = [
                r
                for cluster in rng.choice(clusters, len(clusters), replace=True)
                for r in rows
                if r["cluster"] == cluster
            ]
            samples.append(direction * (value(selected, "after") - value(selected, "before")))
        summary[name] = {
            "cases": len(rows),
            "independent_clusters": len(clusters),
            "before": value(rows, "before"),
            "after": value(rows, "after"),
            "improvement": direction * (value(rows, "after") - value(rows, "before")),
            "exploratory_cluster_bootstrap_95pct": np.percentile(samples, [2.5, 97.5]).tolist(),
            "per_case": rows,
        }
    return {
        "protocol": "music-studio-component-v1",
        "paired_cases": len(old.keys() & new.keys()),
        "expected_cases": len(expected),
        "missing": missing,
        "summary": summary,
        "regressions_over_5pp": regressions,
        "note": "Positive improvement is better; CI is exploratory on this small, "
        "previously seen engineering suite.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/suite-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    result = compare(
        read_json(args.baseline),
        read_json(args.candidate),
        read_json(args.manifest),
        allow_partial=args.allow_partial,
    )
    from music_studio.io import sha256

    for path in (args.baseline, args.candidate):
        if read_json(path).get("suite_sha256") != sha256(args.manifest):
            raise ValueError("Report suite checksum does not match --manifest; rescore first")
    write_json(args.output, result)
    print(f"Paired {result['paired_cases']}/{result['expected_cases']} cases; {args.output}")
    for name, row in result["summary"].items():
        print(
            f"{name}: {row['before']:.4f} -> {row['after']:.4f} "
            f"(improvement {row['improvement']:+.4f})"
        )


if __name__ == "__main__":
    main()
