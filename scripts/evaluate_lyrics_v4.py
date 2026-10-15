"""Reproducible CPU-only anchor ablation on unchanged measured ASR transcripts.

No reference text enters the engine. References are loaded only after predictions
have been saved. Cold/warm neural runtime is inherited and is not ablation speed.
"""

import argparse
from pathlib import Path

import numpy as np
from benchmark_lib import edit_alignment, load_reference, normalize, score_case, tokens

from music_studio.backends.lyric_anchors import GUIDES, supplement_anchors, transfer_anchors
from music_studio.backends.lyric_phrasing import phrase_lyrics
from music_studio.io import read_json, sha256, write_json
from music_studio.review import review_summary
from music_studio.schema import Lyrics


def samples(reference, lyrics):
    ref = [w for w in reference["words"] if normalize(w["text"])]
    hyp = [w for line in lyrics.segments for w in line.words if normalize(w.text)]
    matched = edit_alignment([normalize(w["text"]) for w in ref], [normalize(w.text) for w in hyp])
    return [abs(ref[a]["start"] - hyp[b].start) for a, b in matched["matches"]], len(ref)


def summarize(rows):
    groups = {}
    for row in rows:
        key = f"{row['dataset']}/{row['language']}/{row['split']}/{row['candidate']}"
        groups.setdefault(key, []).append(row)
    result = {}
    for key, selected in groups.items():
        count = sum(r["metrics"]["lyrics"]["reference_tokens"] for r in selected)
        errors = sum(r["metrics"]["lyrics"]["errors"] for r in selected)
        reference = sum(r["reference_time_units"] for r in selected)
        onset = [value for r in selected for value in r["_onset_errors"]]
        result[key] = {
            "cases": len(selected),
            "reference_tokens": count,
            "text_error_rate": errors / count,
            "substitutions": sum(r["metrics"]["lyrics"]["substitutions"] for r in selected),
            "deletions": sum(r["metrics"]["lyrics"]["deletions"] for r in selected),
            "insertions": sum(r["metrics"]["lyrics"]["insertions"] for r in selected),
            "reference_time_units": reference,
            "matched_timed_units": len(onset),
            "timed_exact_match_coverage": len(onset) / reference,
            "correct_onset_200ms_of_all_references": sum(x <= 0.2 for x in onset) / reference,
            "onset_mae_seconds": float(np.mean(onset)) if onset else None,
            "onset_p90_seconds": float(np.quantile(onset, 0.9)) if onset else None,
            "review_counts": {
                k: sum(r["review"]["counts"][k] for r in selected)
                for k in ("text", "timing", "pending")
            },
        }
    return result


def paired_cluster_interval(rows):
    """Descriptive paired bootstrap: (cluster, before count, after count, references)."""
    groups = {}
    for cluster, before, after, references in rows:
        groups.setdefault(cluster, np.zeros(3))[:] += (before, after, references)
    values = np.asarray(list(groups.values()))
    if not len(values) or np.any(values[:, 2] <= 0):
        raise ValueError("Bootstrap requires nonempty reference clusters")
    selected = np.random.default_rng(20261015).integers(len(values), size=(10000, len(values)))
    pooled = values[selected].sum(axis=1)
    deltas = (pooled[:, 1] - pooled[:, 0]) / pooled[:, 2]
    return {
        "delta_after_minus_before": float((values[:, 1] - values[:, 0]).sum() / values[:, 2].sum()),
        "lower_95": float(np.quantile(deltas, 0.025)),
        "upper_95": float(np.quantile(deltas, 0.975)),
        "clusters": len(values),
        "samples": 10000,
        "seed": 20261015,
        "scope": "Descriptive paired cluster bootstrap on a small, non-hidden confirmation set",
    }


def recognition_summary(runs, manifest):
    """Pool S/D/I by the frozen split; never average per-song CERs."""
    expected = {case["id"]: case["split"] for case in manifest["cases"]}
    groups, sources, measured = {}, {}, {}
    for candidate, name in [("small", "mir-small-v4"), ("qwen", "mir-qwen-dual-v4")]:
        report_path = runs / name / "report.json"
        report = read_json(report_path)
        if report["missing_cases"] or report["scoring_errors"]:
            raise ValueError("Recognition comparison contains unreported failures")
        if {case["id"] for case in report["cases"]} != set(expected):
            raise ValueError("Recognition comparison must account for the entire frozen split")
        sources[name] = sha256(report_path)
        measured[candidate] = {case["id"]: case["metrics"]["lyrics"] for case in report["cases"]}
        for split in ("development", "confirmation", "all"):
            selected = [
                case["metrics"]["lyrics"]
                for case in report["cases"]
                if split == "all" or expected[case["id"]] == split
            ]
            total = sum(case["reference_tokens"] for case in selected)
            groups[f"mir1k/zh/{split}/{candidate}"] = {
                "cases": len(selected),
                "reference_tokens": total,
                "errors": sum(case["errors"] for case in selected),
                "cer": sum(case["errors"] for case in selected) / total,
                **{
                    key: sum(case[key] for case in selected)
                    for key in ("substitutions", "deletions", "insertions")
                },
            }
    paired = [
        (
            case.get("group", case["id"]),
            measured["small"][case["id"]]["errors"],
            measured["qwen"][case["id"]]["errors"],
            measured["qwen"][case["id"]]["reference_tokens"],
        )
        for case in manifest["cases"]
        if case["split"] == "confirmation"
    ]
    return {
        "summary": groups,
        "measured_report_sha256": sources,
        "failed_cases": 0,
        "confirmation_cer_change": paired_cluster_interval(paired),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path(".artifacts/benchmark/runs"))
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/data"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mir-only", action="store_true", help="Evaluate only the new MIR-1K runs")
    args = parser.parse_args()
    args.output = args.output or Path(
        "benchmarks/results/lyrics-v4-mir-only.json"
        if args.mir_only
        else "benchmarks/results/lyrics-v4-summary.json"
    )
    rows, manifests = [], {}
    suites = [
        ("suite-v1.json", "lyrics-qwen-production-v3"),
        ("suite-v2-mir1k.json", "mir-qwen-dual-v4"),
    ]
    for filename, production in suites[1:] if args.mir_only else suites:
        manifest_path = Path("benchmarks") / filename
        manifest = read_json(manifest_path)
        manifests[filename] = {"sha256": sha256(manifest_path), "cases": len(manifest["cases"])}
        for case in manifest["cases"]:
            folder = args.runs / production / case["id"]
            parent = read_json(folder / "prediction.json")
            if "lyrics" not in parent:
                continue
            native_path = folder / "analysis/lyrics-input.json"
            native = Lyrics.model_validate(read_json(native_path))
            if tokens(" ".join(line.text for line in native.segments), case["language"]) != tokens(
                " ".join(line["text"] for line in parent["lyrics"]["segments"]), case["language"]
            ):
                raise ValueError("Native recognition text differs from measured output")
            guides, provenance = [], []
            for model, run in [
                ("small", "lyrics-small-seeded-v3"),
                ("large-v3-turbo", "lyrics-turbo-seeded-v3"),
            ]:
                if case["dataset"] == "mir1k":
                    guide_path = (
                        folder / f"analysis/anchor-guide{'-turbo' if model != 'small' else ''}.json"
                    )
                    cache = read_json(guide_path)
                    if cache["audio_sha256"] != sha256(folder / "audio/vocals.wav"):
                        raise ValueError("Cached acoustic guide uses different audio")
                    if cache["model_revision"] != GUIDES[model] or cache["seed"] != 0:
                        raise ValueError("Cached guide model/seed changed")
                    guide = Lyrics.model_validate(cache["lyrics"])
                else:
                    guide_root = args.runs / run / case["id"]
                    guide_path = guide_root / "analysis/lyrics.json"
                    record = read_json(guide_root / "benchmark-run.json")
                    if record["settings"]["asr_revision"] != GUIDES[model]:
                        raise ValueError("Acoustic guide revision changed")
                    if sha256(folder / "audio/vocals.wav") != sha256(
                        guide_root / "audio/vocals.wav"
                    ):
                        raise ValueError("Acoustic guide uses different audio")
                    if sha256(guide_path) not in record["stages"]["lyrics"]["artifacts"].values():
                        raise ValueError("Measured acoustic guide was modified")
                    guide = Lyrics.model_validate(read_json(guide_path))
                guides.append(guide)
                provenance.append(
                    {"model": model, "revision": GUIDES[model], "sha256": sha256(guide_path)}
                )
            # The audio duration is read from the measured run, not from gold labels.
            duration = read_json(folder / "benchmark-run.json")["audio"]["duration"]
            first, second = [
                transfer_anchors(native, g, duration, preserve_lines=True) for g in guides
            ]
            predictions = {
                "small": phrase_lyrics(first),
                "dual": phrase_lyrics(supplement_anchors(first, second)),
            }
            for candidate, lyrics in predictions.items():
                if tokens(
                    " ".join(line.text for line in native.segments), case["language"]
                ) != tokens(" ".join(line.text for line in lyrics.segments), case["language"]):
                    raise ValueError("Display phrasing changed recognized text")
                destination = args.runs / "anchor-ablation-v4" / case["id"] / f"{candidate}.json"
                write_json(destination, lyrics.model_dump())
            # References are used only for scoring already-created predictions.
            reference = load_reference(case, args.data)
            for candidate, lyrics in predictions.items():
                metrics = score_case(case, reference, {"lyrics": lyrics.model_dump()})
                onset, total = samples(reference, lyrics)
                rows.append(
                    {
                        "id": case["id"],
                        "dataset": case["dataset"],
                        "language": case["language"],
                        "split": case.get("split", "regression"),
                        "candidate": candidate,
                        "metrics": metrics,
                        "reference_time_units": total,
                        "_onset_errors": onset,
                        "review": review_summary(lyrics),
                        "native_sha256": sha256(native_path),
                        "audio_sha256": sha256(folder / "audio/vocals.wav"),
                        "guides": provenance,
                        "prediction_sha256": sha256(
                            args.runs / "anchor-ablation-v4" / case["id"] / f"{candidate}.json"
                        ),
                    }
                )
    summary = summarize(rows)
    recognition = recognition_summary(args.runs, read_json(Path("benchmarks/suite-v2-mir1k.json")))
    pairs = {}
    for row in rows:
        if row["dataset"] == "mir1k" and row["split"] == "confirmation":
            pairs.setdefault(row["id"], {})[row["candidate"]] = row
    cluster_ids = {
        c["id"]: c["group"] for c in read_json(Path("benchmarks/suite-v2-mir1k.json"))["cases"]
    }
    onset_interval = paired_cluster_interval(
        [
            (
                cluster_ids[identifier],
                sum(x <= 0.2 for x in pair["small"]["_onset_errors"]),
                sum(x <= 0.2 for x in pair["dual"]["_onset_errors"]),
                pair["small"]["reference_time_units"],
            )
            for identifier, pair in pairs.items()
        ]
    )
    before, after = [summary[f"mir1k/zh/confirmation/{mode}"] for mode in ("small", "dual")]
    gate = {
        "unchanged_recognition_text": all(
            summary[key]["text_error_rate"]
            == summary[key.replace("/small", "/dual")]["text_error_rate"]
            for key in summary
            if key.endswith("/small")
        ),
        "confirmation_end_to_end_onset_not_worse": after["correct_onset_200ms_of_all_references"]
        >= before["correct_onset_200ms_of_all_references"],
        "confirmation_coverage_not_worse": after["timed_exact_match_coverage"]
        >= before["timed_exact_match_coverage"],
    }
    for row in rows:
        row.pop("_onset_errors")
        row["review"] = row["review"]["counts"]
    sources = [
        Path(__file__),
        Path("scripts/benchmark_lib.py"),
        *Path("src/music_studio/backends").glob("lyric_*.py"),
    ]
    source_root = Path(__file__).resolve().parents[1]
    write_json(
        args.output,
        {
            "protocol": "lyrics-v4",
            "manifests": manifests,
            "scope": (
                "CPU-only timing ablation on fixed ASR and cached neural guides; "
                "no inference speed claim"
            ),
            "normalization": "NFKC and punctuation normalization; no Chinese script conversion",
            "chinese_timing_limit": (
                "Exact acoustic-unit/character matches only; multi-character units "
                "are not split into fabricated character timestamps"
            ),
            "accounted_cases": sum(m["cases"] for m in manifests.values()),
            "lyric_cases": len(rows) // 2,
            "unchanged_non_lyric_cases": sum(m["cases"] for m in manifests.values())
            - len(rows) // 2,
            "summary": summary,
            "recognition": recognition,
            "confirmation_onset200_change": onset_interval,
            "promotion_checks": gate,
            "source_hashes": {
                p.resolve().relative_to(source_root).as_posix(): sha256(p) for p in sources
            },
            "cases": rows,
        },
    )
    print(summary)
    print("Promotion checks:", gate)


if __name__ == "__main__":
    main()
