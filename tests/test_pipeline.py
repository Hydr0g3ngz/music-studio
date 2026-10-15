import numpy as np
import pytest
import soundfile as sf

from music_studio.config import Settings
from music_studio.io import read_json, write_json
from music_studio.pipeline import analyze
from music_studio.validation import validate_project


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """Deterministic adapters isolate orchestration failures; real models use smoke_test.py."""
    source = tmp_path / "input.wav"
    sf.write(source, np.zeros((44100, 2)), 44100)
    output = tmp_path / "project"
    calls = []
    failure = {"stage": None}
    monkeypatch.setattr(
        "music_studio.pipeline.installed_versions", lambda names: dict.fromkeys(names, "test")
    )

    def worker(request, log_path):
        stage = request["stage"]
        calls.append(stage)
        if failure["stage"] == stage:
            raise RuntimeError("injected stage failure")
        root = output
        if stage == "separate":
            for stem in ("vocals", "instrumental"):
                sf.write(root / f"audio/{stem}.wav", np.zeros((44100, 2)), 44100)
            result = {"files": ["audio/vocals.wav", "audio/instrumental.wav"]}
        elif stage == "lyrics":
            result = {"language": "en", "timing_method": "test", "segments": []}
        elif stage == "melody":
            result = {"backend": "test", "notes": []}
            write_json(
                root / "analysis/pitch.json", {"times": [], "frequency_hz": [], "periodicity": []}
            )
        elif stage == "rhythm":
            result = {"backend": "test", "bpm": 120, "beats": [0.25, 0.75]}
        else:
            result = {
                "backend": "test",
                "chords": [{"start": 0, "end": 1, "label": "N", "score": 0}],
            }
        write_json(request["result"], result)
        write_json(request["result"].with_suffix(".metrics.json"), {"elapsed_seconds": 0})
        return result

    # Workers receive serialized string paths, like the real subprocess adapter.
    def wrapper(request, log_path):
        from pathlib import Path

        request["result"] = Path(request["result"])
        return worker(request, log_path)

    monkeypatch.setattr("music_studio.pipeline.run_worker", wrapper)
    return source, output, calls, failure


def test_resume_after_failure_and_cache_invalidation(engine):
    source, output, calls, failure = engine
    failure["stage"] = "melody"
    with pytest.raises(RuntimeError, match="injected"):
        analyze(source, output, Settings(), progress=lambda _: None)
    assert read_json(output / "run.json")["status"] == "failed"
    assert not (output / "project.json").exists()
    calls.clear()
    failure["stage"] = None
    analyze(source, output, Settings(), resume=True, progress=lambda _: None)
    assert calls == ["melody", "rhythm", "harmony"]
    assert validate_project(output)["valid"]
    calls.clear()
    analyze(source, output, Settings(language="zh"), resume=True, progress=lambda _: None)
    assert calls == ["lyrics"]
    (output / "audio/vocals.wav").write_bytes(b"corrupted")
    calls.clear()
    analyze(source, output, Settings(language="zh"), resume=True, progress=lambda _: None)
    assert calls == ["separate"]
    assert validate_project(output)["valid"]


def test_existing_output_and_different_source_are_protected(engine):
    source, output, _, _ = engine
    analyze(source, output, Settings(), progress=lambda _: None)
    with pytest.raises(ValueError, match="--resume"):
        analyze(source, output, Settings(), progress=lambda _: None)
    sf.write(source, np.ones((44100, 2)) * 0.1, 44100)
    with pytest.raises(ValueError, match="different audio"):
        analyze(source, output, Settings(), resume=True, progress=lambda _: None)
