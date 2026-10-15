"""Adapters and transparent metrics for the frozen public regression suite."""

from __future__ import annotations

import math
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

from music_studio.io import read_json, sha256, write_json

SILENCES = {"", "SP", "AP", "SIL", "<SP>", "<AP>", "<SIL>", "_NONE"}


def local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path is outside the dataset directory: {relative}")
    return path


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = text.replace("'", "").replace("’", "")
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


def tokens(text: str, language: str) -> list[str]:
    text = normalize(text)
    return list(text.replace(" ", "")) if language == "zh" else text.split()


def edit_alignment(reference: list[str], hypothesis: list[str]) -> dict:
    """Levenshtein alignment. Exact monotonic matches also support timing comparisons."""
    matrix = np.zeros((len(reference) + 1, len(hypothesis) + 1), dtype=np.int32)
    matrix[:, 0] = np.arange(len(reference) + 1)
    matrix[0, :] = np.arange(len(hypothesis) + 1)
    for i, ref in enumerate(reference, 1):
        for j, hyp in enumerate(hypothesis, 1):
            matrix[i, j] = min(
                matrix[i - 1, j] + 1,
                matrix[i, j - 1] + 1,
                matrix[i - 1, j - 1] + (ref != hyp),
            )
    i, j = len(reference), len(hypothesis)
    matches, substitutions, deletions, insertions = [], 0, 0, 0
    while i or j:
        if (
            i
            and j
            and matrix[i, j] == matrix[i - 1, j - 1] + (reference[i - 1] != hypothesis[j - 1])
        ):
            if reference[i - 1] == hypothesis[j - 1]:
                matches.append((i - 1, j - 1))
            else:
                substitutions += 1
            i, j = i - 1, j - 1
        elif i and matrix[i, j] == matrix[i - 1, j] + 1:
            deletions += 1
            i -= 1
        else:
            insertions += 1
            j -= 1
    return {
        "errors": int(matrix[-1, -1]),
        "reference_tokens": len(reference),
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "matches": matches[::-1],
    }


def timing_metrics(reference: list[dict], hypothesis: list[dict]) -> dict:
    # A multi-character model token keeps its original interval. Never invent character times.
    ref = [w for w in reference if normalize(w["text"])]
    hyp = [w for w in hypothesis if normalize(w["text"])]
    alignment = edit_alignment(
        [normalize(w["text"]) for w in ref], [normalize(w["text"]) for w in hyp]
    )
    onset, offset = [], []
    for i, j in alignment["matches"]:
        onset.append(abs(hyp[j]["start"] - ref[i]["start"]))
        if ref[i].get("end") is not None and math.isfinite(ref[i]["end"]):
            offset.append(abs(hyp[j]["end"] - ref[i]["end"]))
    return {
        "reference_words": len(ref),
        "matched_words": len(onset),
        "matched_reference_fraction": len(onset) / len(ref) if ref else None,
        "onset_mae_seconds": float(np.mean(onset)) if onset else None,
        "onset_median_seconds": float(np.median(onset)) if onset else None,
        "onset_p90_seconds": float(np.percentile(onset, 90)) if onset else None,
        "onset_within_200ms_fraction_of_matches": (
            float(np.mean(np.asarray(onset) <= 0.2)) if onset else None
        ),
        "offset_reference_matches": len(offset),
        "offset_mae_seconds": float(np.mean(offset)) if offset else None,
        "scope": "Exact-text monotonic matches only; errors must be read with match coverage.",
    }


def _jsonl_item(path: Path, key: str) -> dict:
    import json

    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("name", Path(record.get("file_name", "")).stem) == key:
            return record
    raise ValueError(f"Missing reference {key} in {path.name}")


def multitrack_reference(path: Path) -> dict:
    """Decode the five published STEMS streams without trimming or changing their origins."""
    import av

    chunks = [[] for _ in range(5)]
    with av.open(str(path)) as container:
        streams = list(container.streams.audio)
        if len(streams) != 5:
            raise ValueError("Expected mix, drums, bass, other, vocals in the STEMS container")
        indices = {stream.index: index for index, stream in enumerate(streams)}
        resamplers = [
            av.AudioResampler(format="fltp", layout="stereo", rate=44100) for _ in streams
        ]
        for packet in container.demux(streams):
            index = indices[packet.stream.index]
            for frame in packet.decode():
                frame.pts = None
                chunks[index].extend(
                    converted.to_ndarray().T for converted in resamplers[index].resample(frame)
                )
        for index, resampler in enumerate(resamplers):
            chunks[index].extend(converted.to_ndarray().T for converted in resampler.resample(None))
    signals = [np.concatenate(parts) for parts in chunks]
    if len({len(signal) for signal in signals}) != 1:
        raise ValueError("Decoded STEMS stream lengths differ")
    if not all(np.isfinite(signal).all() for signal in signals):
        raise ValueError("STEMS audio contains non-finite values")
    return {
        "duration": len(signals[0]) / 44100,
        "sample_rate": 44100,
        "mixture": signals[0],
        "vocals": signals[4],
        "instrumental": signals[1] + signals[2] + signals[3],
    }


def si_sdr(reference: np.ndarray, estimate: np.ndarray) -> float | None:
    if reference.shape != estimate.shape:
        raise ValueError("Separation signals must have identical sample counts and channels")
    ref, hyp = reference.astype(np.float64).ravel(), estimate.astype(np.float64).ravel()
    ref, hyp = ref - ref.mean(), hyp - hyp.mean()
    energy = float(ref @ ref)
    if energy < 1e-12:
        return None
    if float(hyp @ hyp) < 1e-12:
        return -120.0
    target = ref * float(hyp @ ref) / energy
    error = hyp - target
    return float(10 * np.log10((target @ target + 1e-12) / (error @ error + 1e-12)))


def load_reference(case: dict, root: Path) -> dict:
    spec = case["reference"]
    if spec["format"] == "musdb7":
        return multitrack_reference(local_path(root, spec["path"]))
    audio = sf.info(local_path(root, case["audio"]))
    result = {"duration": audio.duration, "sample_rate": audio.samplerate}
    if spec["format"] == "jamalt+jamendo":
        transcript = _jsonl_item(local_path(root, spec["transcript"]), spec["key"])
        alignment = _jsonl_item(local_path(root, spec["alignment"]), spec["key"])
        result.update(text=transcript["text"], lines=transcript["lines"], words=alignment["words"])
    elif spec["format"] == "gtsinger":
        data = read_json(local_path(root, spec["path"]))
        words, notes = [], []
        for word in data:
            if word["word"].upper() not in SILENCES:
                words.append(
                    {
                        "text": word["word"],
                        "start": word["start_time"],
                        "end": word["end_time"],
                    }
                )
            pitches, starts, ends = word["note"], word["note_start"], word["note_end"]
            for pitch, start, end in zip(pitches, starts, ends, strict=True):
                if pitch > 0 and end > start:
                    notes.append({"pitch": pitch, "start": start, "end": end})
        separator = "" if case["language"] == "zh" else " "
        result.update(text=separator.join(w["text"] for w in words), words=words, notes=notes)
    elif spec["format"] == "mir1k-partial-align":
        record = next(
            row
            for row in read_json(local_path(root, spec["path"]))
            if row["song_id"] == spec["key"]
        )
        if len(record["lyric"]) != len(record["on_offset"]):
            raise ValueError("MIR-1K character/time count mismatch")
        result.update(
            text=record["lyric"],
            words=[
                {"text": text, "start": start, "end": end}
                for text, (start, end) in zip(record["lyric"], record["on_offset"], strict=True)
            ],
        )
    elif spec["format"] == "guitarset":
        jams = read_json(local_path(root, spec["path"]))
        beats = next(a for a in jams["annotations"] if a["namespace"] == "beat_position")
        chords = [a for a in jams["annotations"] if a["namespace"] == "chord"]
        # GuitarSet 1.1.0 stores lead-sheet chords first, inferred performed chords second.
        # This matches mirdata.datasets.guitarset.load_chords(leadsheet_version=False).
        if len(chords) != 2 or "manual verification" not in str(chords[1]["annotation_metadata"]):
            raise ValueError("Unexpected performed-chord annotation in GuitarSet")
        result.update(
            beats=[d["time"] for d in beats["data"]],
            chords=[
                {"start": d["time"], "end": d["time"] + d["duration"], "label": d["value"]}
                for d in chords[1]["data"]
                if d["duration"] > 0
            ],
        )
    else:
        raise ValueError(f"Unknown reference format: {spec['format']}")
    for name in ("words", "lines", "notes", "chords"):
        for item in result.get(name, []):
            if not math.isfinite(item["start"]) or item["start"] < -0.05:
                raise ValueError(f"Invalid {name} start in {case['id']}")
            end = item.get("end")
            if end is not None and math.isfinite(end):
                if end < item["start"] or end > audio.duration + 0.05:
                    raise ValueError(f"Invalid {name} end in {case['id']}: {end}")
    return result


def validate_suite(manifest: dict, root: Path) -> dict:
    for asset in manifest["assets"]:
        path = local_path(root, asset["path"])
        if not path.is_file() or path.stat().st_size != asset["bytes"]:
            raise ValueError(f"Missing or incomplete file: {asset['path']}")
        if sha256(path) != asset["sha256"]:
            raise ValueError(f"Checksum mismatch: {asset['path']}")
    inventory = []
    for case in manifest["cases"]:
        reference = load_reference(case, root)
        inventory.append(
            {
                "id": case["id"],
                "dataset": case["dataset"],
                "domain": case["domain"],
                "language": case["language"],
                "duration": reference["duration"],
                "words": len(reference.get("words", [])),
                "notes": len(reference.get("notes", [])),
                "beats": len(reference.get("beats", [])),
                "chords": len(reference.get("chords", [])),
            }
        )
    result = {"valid": True, "cases": inventory, "asset_count": len(manifest["assets"])}
    write_json(root.parent / "inventory.json", result)
    return result


def score_case(
    case: dict, reference: dict, prediction: dict, prediction_root: Path | None = None
) -> dict:
    import mir_eval

    metrics = {}
    duration = reference.get("duration", float("inf"))
    # Resampling 44.1k -> 22.05k/16k can round the final sample up. This is not a
    # timestamp shift: allow one 16k sample at the end, never a beat/frame-sized drift.
    tolerance = 1 / 16000
    intervals = [
        *prediction.get("lyrics", {}).get("segments", []),
        *prediction.get("melody", {}).get("notes", []),
        *prediction.get("harmony", {}).get("chords", []),
    ]
    for item in intervals:
        if not (
            math.isfinite(item["start"])
            and math.isfinite(item["end"])
            and 0 <= item["start"] < item["end"] <= duration + tolerance
        ):
            raise ValueError("Prediction interval is nonfinite, inverted or outside source audio")
    beats = prediction.get("rhythm", {}).get("beats", [])
    if any(not math.isfinite(t) or not 0 <= t < duration for t in beats) or any(
        right <= left for left, right in zip(beats, beats[1:], strict=False)
    ):
        raise ValueError("Prediction beats are unordered or outside source audio")
    if "lyrics" in prediction and "text" in reference:
        lyrics = prediction["lyrics"]["segments"]
        text = " ".join(line["text"] for line in lyrics)
        aligned = edit_alignment(
            tokens(reference["text"], case["language"]), tokens(text, case["language"])
        )
        metrics["lyrics"] = {k: v for k, v in aligned.items() if k != "matches"}
        metrics["lyrics"].update(
            metric="normalized_cer" if case["language"] == "zh" else "normalized_wer",
            rate=aligned["errors"] / aligned["reference_tokens"],
            normalization=(
                "NFKC, casefold, punctuation removed, apostrophes collapsed; no script conversion"
            ),
        )
        words = [w for line in lyrics for w in line["words"]]
        metrics["word_timing"] = timing_metrics(reference["words"], words)
    if "melody" in prediction and reference.get("notes"):
        ref, hyp = reference["notes"], prediction["melody"]["notes"]

        def intervals(ns):
            return np.asarray([[n["start"], n["end"]] for n in ns]).reshape(-1, 2)

        def pitches(ns):
            return np.asarray([440 * 2 ** ((n["pitch"] - 69) / 12) for n in ns])

        for label, offset in (("note_onset_pitch", None), ("note_onset_offset_pitch", 0.2)):
            precision, recall, f1, _ = mir_eval.transcription.precision_recall_f1_overlap(
                intervals(ref), pitches(ref), intervals(hyp), pitches(hyp), offset_ratio=offset
            )
            metrics[label] = {"precision": precision, "recall": recall, "f1": f1}
        metrics["note_tolerances"] = {
            "onset_seconds": 0.05,
            "pitch_cents": 50,
            "offset": "max(50 ms, 20% of reference note duration)",
            "reference": "Published note_start/note_end, not quantized note_dur",
        }
        metrics["note_counts"] = {"reference": len(ref), "estimated": len(hyp)}
    if "rhythm" in prediction and reference.get("beats"):
        result = mir_eval.beat.evaluate(
            np.asarray(reference["beats"]), np.asarray(prediction["rhythm"]["beats"])
        )
        metrics["beats"] = {
            "F-measure": result["F-measure"],
            "CMLt": result["Correct Metric Level Total"],
            "AMLt": result["Any Metric Level Total"],
        }
        metrics["beats"]["scope"] = "mir_eval defaults: first 5 seconds excluded, 70 ms F tolerance"
    if "harmony" in prediction and reference.get("chords"):
        ref, hyp = reference["chords"], prediction["harmony"]["chords"]

        # Project labels use C/Cm, while mir_eval uses Harte C:maj/C:min.
        def label(value):
            if value in ("N", "X") or ":" in value:
                return value
            return value[:-1] + ":min" if value.endswith("m") else value + ":maj"

        def chord_input(chords):
            return (
                np.asarray([[c["start"], c["end"]] for c in chords]),
                [label(c["label"]) for c in chords],
            )

        ri, rl = chord_input(ref)
        hi, hl = chord_input(hyp)
        hi, hl = mir_eval.util.adjust_intervals(
            hi, hl, t_min=ri[0, 0], t_max=ri[-1, 1], start_label="N", end_label="N"
        )
        scores = mir_eval.chord.evaluate(ri, rl, hi, hl)
        metrics["chords"] = {key: scores[key] for key in ("root", "majmin")}
        merged, ref_labels, hyp_labels = mir_eval.util.merge_labeled_intervals(ri, rl, hi, hl)
        durations = mir_eval.util.intervals_to_durations(merged)
        eligible = mir_eval.chord.majmin(ref_labels, hyp_labels) >= 0
        metrics["chords"]["majmin_scored_reference_fraction"] = float(
            durations[eligible].sum() / durations.sum()
        )
        metrics["chords"]["scope"] = (
            "Duration-weighted root and major/minor reduction; performed chords"
        )
    if "separation" in prediction:
        if prediction_root is None:
            raise ValueError("Prediction directory is required to score separation audio")
        separation = {}
        for name in ("vocals", "instrumental"):
            estimate, rate = sf.read(
                local_path(prediction_root, prediction["separation"][name]),
                dtype="float32",
                always_2d=True,
            )
            if rate != reference["sample_rate"]:
                raise ValueError("Separation estimate and reference sample rates differ")
            value = si_sdr(reference[name], estimate)
            baseline = si_sdr(reference[name], reference["mixture"])
            separation[name] = {
                "si_sdr_db": value,
                "mixture_si_sdr_db": baseline,
                "si_sdri_db": value - baseline
                if value is not None and baseline is not None
                else None,
            }
        separation["scope"] = (
            "Seven-second AAC previews; stereo flattened after mean removal; "
            "no time-shift fitting. Not SiSEC BSS Eval SDR or a full-song benchmark."
        )
        metrics["separation"] = separation
    return metrics
