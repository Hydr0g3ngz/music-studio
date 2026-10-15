import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from music_studio.schema import Melody, Note

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_frozen_vocadito_manifest_matches_published_experiment_identity():
    root = SCRIPTS.parent
    manifest = root / "benchmarks/vocadito-v1.json"
    report = json.loads(
        (root / "benchmarks/results/melody-next-2026-10-16.json").read_text(encoding="utf-8")
    )
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == report["vocadito"]["suite_sha256"]
    cases = json.loads(manifest.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 40
    assert all(case["files"]["A1"] != case["files"]["A2"] for case in cases)


def test_note_and_contour_scoring_handles_unvoiced_null_and_both_annotators(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("vocadito_eval", SCRIPTS / "evaluate_vocadito.py")
    evaluator = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(evaluator)
    finally:
        sys.path.remove(str(SCRIPTS))
    for name in ("A1", "A2"):
        np.savetxt(tmp_path / f"{name}.csv", [[0.2, 440, 0.5]], delimiter=",")
    np.savetxt(tmp_path / "f0.csv", [[0, 0], [0.1, 0], [0.2, 440], [0.3, 440]], delimiter=",")
    melody = Melody(
        backend="known-truth", notes=[Note(id="n", start=0.2, end=0.7, pitch=69, score=1)]
    )
    result = evaluator.score(
        tmp_path,
        {"files": {"A1": "A1.csv", "A2": "A2.csv", "f0": "f0.csv"}},
        melody,
        [0, 0.1, 0.2, 0.3],
        [None, None, 440, 440],
    )
    assert result["A1"]["onset_pitch"]["f1"] == 1
    assert result["A2"]["onset_offset_pitch"]["f1"] == 1
    assert result["f0"]["Voicing False Alarm"] == 0
    assert result["f0"]["Raw Pitch Accuracy"] == 1
