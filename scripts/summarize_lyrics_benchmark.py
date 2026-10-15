"""Pool actual word timing errors without averaging per-song medians or percentiles."""

import argparse
from pathlib import Path

import numpy as np
from benchmark_lib import edit_alignment, load_reference, normalize

from music_studio.io import read_json, sha256, write_json


def summarize(run: Path, cases: list[dict], references: dict, suite_hash: str) -> dict:
    report = read_json(run / "report.json")
    if report["suite_sha256"] != suite_hash:
        raise ValueError(f"Different suite: {run.name}")
    if report["missing_cases"] or report["scored_cases"] != len(cases):
        raise ValueError(f"Incomplete run: {run.name}")
    groups = {}
    for case in cases:
        if case["id"] not in references:
            continue
        folder = run / case["id"]
        prediction = read_json(folder / "prediction.json")["lyrics"]
        record = read_json(folder / "benchmark-run.json")
        lyric_path = folder / "analysis/lyrics.json"
        expected = record["stages"]["lyrics"]["artifacts"]["analysis/lyrics.json"]
        if sha256(lyric_path) != expected or read_json(lyric_path) != prediction:
            raise ValueError(f"Changed prediction: {run.name}/{case['id']}")
        key = f"{case['dataset']}/{case['language']}"
        group = groups.setdefault(
            key,
            {
                "cases": 0,
                "reference_words": 0,
                "onsets": [],
                "offsets": [],
                "predicted_timed_words": 0,
                "segments": 0,
                "segments_without_word_times": 0,
                "segments_with_partial_word_times": 0,
                "segments_marked_for_review": 0,
            },
        )
        ref = [w for w in references[case["id"]]["words"] if normalize(w["text"])]
        hyp = [w for s in prediction["segments"] for w in s["words"] if normalize(w["text"])]
        matches = edit_alignment(
            [normalize(w["text"]) for w in ref], [normalize(w["text"]) for w in hyp]
        )["matches"]
        group["onsets"].extend(abs(hyp[j]["start"] - ref[i]["start"]) for i, j in matches)
        group["offsets"].extend(
            abs(hyp[j]["end"] - ref[i]["end"]) for i, j in matches if ref[i].get("end") is not None
        )
        group["cases"] += 1
        group["reference_words"] += len(ref)
        group["predicted_timed_words"] += len(hyp)
        for line in prediction["segments"]:
            group["segments"] += 1
            group["segments_marked_for_review"] += bool(line.get("review_reasons"))
            if not line["words"]:
                group["segments_without_word_times"] += 1
            elif normalize("".join(w["text"] for w in line["words"])).replace(" ", "") != normalize(
                line["text"]
            ).replace(" ", ""):
                group["segments_with_partial_word_times"] += 1
    for key, group in groups.items():
        onsets, offsets = np.array(group.pop("onsets")), group.pop("offsets")
        group.update(
            text_micro_error_rate=report["summary"][key]["micro_error_rate"],
            reference_text_tokens=report["summary"][key]["reference_tokens"],
            matched_words=len(onsets),
            match_coverage=len(onsets) / group["reference_words"],
            onset_mae_seconds=float(np.mean(onsets)) if len(onsets) else None,
            onset_median_seconds=float(np.median(onsets)) if len(onsets) else None,
            onset_p90_seconds=float(np.percentile(onsets, 90)) if len(onsets) else None,
            onset_within_200ms_fraction_of_matches=float(np.mean(onsets <= 0.2))
            if len(onsets)
            else None,
            matched_within_200ms_fraction_of_all_references=int(sum(onsets <= 0.2))
            / group["reference_words"],
            offset_mae_seconds=float(np.mean(offsets)) if offsets else None,
        )
    session = read_json(run / "session.json")
    return {
        "run": run.name,
        "local_scored_report_sha256": sha256(run / "report.json"),
        "groups": groups,
        "performance_scope": session.get("timing_scope", "See source report"),
        "sampled_whole_gpu": session.get("gpu"),
        "complete_cases": report["scored_cases"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path, nargs="+")
    parser.add_argument("--manifest", type=Path, default=Path("benchmarks/suite-v1.json"))
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/data"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = read_json(args.manifest)["cases"]
    references = {
        c["id"]: load_reference(c, args.data)
        for c in cases
        if c["dataset"] in ("jamalt", "gtsinger")
    }
    result = {
        "protocol": "music-studio-lyrics-v3",
        "suite_sha256": sha256(args.manifest),
        "scope": "Engineering subset, training membership unknown. Timing statistics pool "
        "actual exact-word matches; median/P90 are not averages of song quantiles.",
        "runs": [summarize(r, cases, references, sha256(args.manifest)) for r in args.runs],
    }
    write_json(args.output, result)
    print(f"Wrote {len(result['runs'])} complete lyric summaries to {args.output}")


if __name__ == "__main__":
    main()
