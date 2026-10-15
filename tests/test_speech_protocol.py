import hashlib
import json
from pathlib import Path

from music_studio.studio.cleanup import WEIGHTS


def test_frozen_speech_suites_are_disjoint_and_keep_exact_bytes():
    root = Path(__file__).resolve().parents[1]
    expected = [
        (
            "speech-cleanup-v1.json",
            "1efa1d8fa4e49ff0b25049f3c1cd08d052cc2d0c55ce74ea0b1e67bb1c5e88e5",
        ),
        (
            "speech-cleanup-validation-v1.json",
            "1c49f145356c51f181b9f1a14d7d1389f2d35cd4944c85f460fe1118902bdba3",
        ),
    ]
    ids = []
    for name, digest in expected:
        source = root / "benchmarks" / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        manifest = json.loads(source.read_text(encoding="utf-8"))
        assert manifest["license"] == "CC BY 4.0"
        assert len(manifest["samples"]) == 16
        ids.append({s["id"] for s in manifest["samples"]})
        assert {s["speaker"] for s in manifest["samples"]} == {"p232", "p257"}
        for sample in manifest["samples"]:
            assert sample["clean"]["sha256"] != sample["noisy"]["sha256"]
        if "candidates" in manifest:
            for model, config in manifest["candidates"].items():
                assert config["internal_rate"] == WEIGHTS[model]["rate"]
                assert config["tail_padding"] == WEIGHTS[model]["padding"]
                assert config["hop"] == WEIGHTS[model]["hop"]
                assert config["strength"] == 1
    assert len(ids[0] | ids[1]) == 32
