import numpy as np
import pytest

from scripts.benchmark_lib import (
    edit_alignment,
    local_path,
    score_case,
    si_sdr,
    timing_metrics,
    tokens,
)


def test_errors_do_not_shift_all_subsequent_timing_pairs():
    alignment = edit_alignment(["a", "b", "c"], ["a", "extra", "b", "wrong"])
    assert alignment["errors"] == 2
    assert alignment["insertions"] == 1
    assert alignment["substitutions"] == 1
    assert alignment["matches"] == [(0, 0), (1, 2)]
    reference = [
        {"text": "a", "start": 1.0, "end": None},
        {"text": "b", "start": 2.0, "end": 2.5},
        {"text": "c", "start": 3.0, "end": 3.5},
    ]
    hypothesis = [
        {"text": "a", "start": 1.1, "end": 1.4},
        {"text": "extra", "start": 1.5, "end": 1.8},
        {"text": "b", "start": 2.1, "end": 2.6},
        {"text": "wrong", "start": 3.0, "end": 3.5},
    ]
    result = timing_metrics(reference, hypothesis)
    assert result["matched_words"] == 2
    assert result["matched_reference_fraction"] == pytest.approx(2 / 3)
    assert result["onset_mae_seconds"] == pytest.approx(0.1)
    assert result["offset_reference_matches"] == 1


def test_batch_report_accepts_empty_attempts_and_does_not_invent_cold_timing(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    import benchmark

    from music_studio.io import write_json

    output = tmp_path / "run"
    case = {"id": "one", "dataset": "demo", "language": "en", "domain": "singing"}
    write_json(output / "one/prediction.json", {})
    write_json(
        output / "one/benchmark-run.json",
        {
            "status": "complete",
            "attempts": [],
            "executed_stages": ["lyrics"],
            "audio": {"duration": 3},
            "stages": {"lyrics": {"metrics": {"elapsed_seconds": 1}}},
        },
    )
    monkeypatch.setattr(benchmark, "load_reference", lambda *args: {})
    monkeypatch.setattr(benchmark, "score_case", lambda *args: {})
    result = benchmark.report_scores([case], tmp_path, output)
    assert result["scored_cases"] == 1 and result["missing_cases"] == []
    assert result["cases"][0]["performance"]["stages"]["lyrics"]["process_rtf"] is None
    assert "weighted_process_rtf" not in result["runtime"]["lyrics"]
    assert "Cold per-case" in result["runtime"]["lyrics"]["scope"]


def test_chinese_text_scoring_does_not_fabricate_character_times():
    assert tokens("你，好！", "zh") == ["你", "好"]
    result = timing_metrics(
        [{"text": "你", "start": 0, "end": 1}, {"text": "好", "start": 1, "end": 2}],
        [{"text": "你好", "start": 0, "end": 2}],
    )
    assert result["matched_words"] == 0
    assert result["onset_mae_seconds"] is None
    assert result["matched_reference_fraction"] == 0


def test_mirrored_download_checks_member_size_before_decompression(tmp_path, monkeypatch):
    import io
    import zipfile
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    import benchmark

    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("song.wav", b"a" * 10000)
    monkeypatch.setattr(benchmark, "urlopen", lambda *a, **kw: io.BytesIO(content.getvalue()))
    item = {
        "path": "mir/song.wav",
        "bytes": 10,
        "sha256": "unused",
        "url": "https://example.com/audio.zip",
        "archive_format": "zip-download",
        "archive_member_basename": "song.wav",
    }
    with pytest.raises(ValueError, match="member size"):
        benchmark.prepare({"assets": [item], "cases": []}, tmp_path)
    assert not (tmp_path / item["path"]).exists()


def test_new_suite_recognition_summary_pools_errors_by_frozen_split(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    from evaluate_lyrics_v4 import recognition_summary

    from music_studio.io import write_json

    manifest = {
        "cases": [
            {"id": "short", "split": "development"},
            {"id": "long", "split": "development"},
            {"id": "confirm", "split": "confirmation"},
        ]
    }
    report = {
        "missing_cases": [],
        "scoring_errors": [],
        "cases": [
            {
                "id": name,
                "metrics": {
                    "lyrics": {
                        "errors": errors,
                        "reference_tokens": total,
                        "substitutions": errors,
                        "deletions": 0,
                        "insertions": 0,
                    }
                },
            }
            for name, errors, total in [("short", 1, 1), ("long", 0, 9), ("confirm", 2, 10)]
        ],
    }
    for name in ("mir-small-v4", "mir-qwen-dual-v4"):
        write_json(tmp_path / name / "report.json", report)
    result = recognition_summary(tmp_path, manifest)["summary"]
    assert result["mir1k/zh/development/qwen"]["cer"] == 0.1
    assert result["mir1k/zh/confirmation/qwen"]["cer"] == 0.2
    assert result["mir1k/zh/all/qwen"]["reference_tokens"] == 20


def test_paired_cluster_interval_retains_a_constant_effect(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    from evaluate_lyrics_v4 import paired_cluster_interval

    found = paired_cluster_interval([("a", 5, 0, 10), ("b", 10, 0, 20)])
    assert found["delta_after_minus_before"] == -0.5
    assert found["lower_95"] == found["upper_95"] == -0.5
    assert found["clusters"] == 2


def test_report_export_never_assigns_the_authors_hardware_to_an_unknown_run(tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    from export_benchmark_results import publish

    from music_studio.io import write_json

    write_json(
        tmp_path / "run/report.json", {"missing_cases": [], "scoring_errors": [], "cases": []}
    )
    write_json(tmp_path / "run/session.json", {})
    report = publish(tmp_path, tmp_path / "export", "run", "unknown.json")
    assert "gpu" not in report["hardware"]
    verified = {"gpu": "CPU-only", "date": "2026-10-15"}
    report = publish(tmp_path, tmp_path / "export", "run", "known.json", verified)
    assert report["hardware"] == verified


def test_benchmark_paths_cannot_escape_data_directory(tmp_path):
    assert local_path(tmp_path, "audio/song.wav") == tmp_path / "audio/song.wav"
    with pytest.raises(ValueError, match="outside"):
        local_path(tmp_path, "../outside.wav")


def test_separation_metric_is_scale_invariant_and_rejects_misalignment():
    rng = np.random.default_rng(42)
    reference = rng.normal(size=(1000, 2))
    estimate = reference + 0.1 * rng.normal(size=reference.shape)
    assert si_sdr(reference, estimate) == pytest.approx(si_sdr(reference, 2 * estimate))
    assert si_sdr(np.zeros((1000, 2)), estimate) is None
    assert si_sdr(reference, np.zeros_like(reference)) == -120
    with pytest.raises(ValueError, match="identical"):
        si_sdr(reference, estimate[:-1])


def test_mir_eval_adapter_scores_perfect_events():
    pytest.importorskip("mir_eval")
    notes = [{"start": 1.0, "end": 1.5, "pitch": 60}]
    beats = np.arange(0, 15, 0.5).tolist()
    result = score_case(
        {"language": "en"},
        {"notes": notes, "beats": beats, "chords": [{"start": 0, "end": 15, "label": "C:maj"}]},
        {
            "melody": {"notes": notes},
            "rhythm": {"beats": beats},
            "harmony": {"chords": [{"start": 0, "end": 15, "label": "C"}]},
        },
    )
    assert result["note_onset_offset_pitch"]["f1"] == 1
    assert result["beats"]["F-measure"] == 1
    assert result["beats"]["CMLt"] == 1
    assert result["chords"]["majmin"] == 1
    assert result["chords"]["majmin_scored_reference_fraction"] == 1


def test_invalid_prediction_is_reported_instead_of_scored():
    with pytest.raises(ValueError, match="outside"):
        score_case(
            {"language": "en"},
            {"duration": 1},
            {"melody": {"notes": [{"start": 0.5, "end": 1.01, "pitch": 60}]}},
        )
    with pytest.raises(ValueError, match="unordered"):
        score_case({}, {"duration": 1}, {"rhythm": {"beats": [0.5, 0.3]}})


def test_paired_comparisons_reject_missing_and_overlapping_training_cases():
    from scripts.compare_benchmarks import compare

    manifest = {"cases": [{"id": "a", "dataset": "demo", "language": "en"}]}
    row = {"id": "a", "metrics": {"lyrics": {"rate": 0.5, "errors": 5, "reference_tokens": 10}}}
    baseline = {"cases": [row]}
    with pytest.raises(ValueError, match="Incomplete"):
        compare(baseline, {"cases": []}, manifest)
    with pytest.raises(ValueError, match="training overlap"):
        compare(baseline, {"cases": [row], "training_overlap": "seen"}, manifest)
    changed = {"id": "a", "metrics": {"lyrics": {"rate": 0.2, "errors": 2, "reference_tokens": 10}}}
    result = compare(baseline, {"cases": [changed]}, manifest)
    summary = result["summary"]["demo/en/lyrics"]
    assert summary["improvement"] == pytest.approx(0.3)
    assert summary["independent_clusters"] == 1
