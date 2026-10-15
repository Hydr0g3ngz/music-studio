import importlib.util
import sys

from fastapi.testclient import TestClient

from music_studio.config import Settings
from music_studio.io import read_json
from music_studio.ui import runtime
from music_studio.ui.server import create_app


def test_external_probe_and_missing_runtime():
    found = runtime.probe_modules(sys.executable)
    assert set(found) == set(runtime.MODULES)
    assert all(isinstance(value, bool) for value in found.values())
    assert found["torch"] == (importlib.util.find_spec("torch") is not None)
    assert not any(runtime.probe_modules("/nonexistent/lyric-python").values())


def test_whisper_keeps_base_runtime_and_alignment_uses_required_runtime(monkeypatch, tmp_path):
    python = tmp_path / "lyric-python"
    python.touch()
    base = dict.fromkeys(runtime.MODULES, False) | {"torch": True, "faster_whisper": True}
    optional = dict.fromkeys(runtime.MODULES, True)
    monkeypatch.setattr(runtime, "probe_modules", lambda path=None: optional if path else base)
    config = Settings(lyrics_python=str(python)).model_dump()
    assert runtime.runtime_capabilities(config)["qwen"]["available"]
    assert runtime.runtime_error(config, "full") is None
    optional["faster_whisper"] = False
    # Native Whisper still runs in the main environment, even with an optional path configured.
    assert runtime.runtime_error(config, "full") is None
    config.update(asr_backend="qwen", lyrics_alignment="anchors")
    assert runtime.runtime_error(config, "lyrics") == runtime.WHISPER_HELP
    config.update(lyrics_python=None, lyrics_alignment="anchors")
    # Re-aligning corrected text only needs the acoustic guide, not Qwen recognition.
    assert runtime.runtime_error(config, "align") is None
    config.update(lyrics_alignment="qwen")
    assert runtime.runtime_error(config, "align") == runtime.ALIGN_HELP


def test_unavailable_qwen_rejected_before_creating_work_or_changing_job(tmp_path, monkeypatch):
    original_find = importlib.util.find_spec

    def find_spec(name, *args, **kwargs):
        if name in ("torch", "demucs", "faster_whisper"):
            return object()
        if name in ("qwen_asr", "transformers"):
            return None
        return original_find(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)
    app = create_app(tmp_path, Settings())
    record, _ = app.state.manager.create("song.wav")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        capabilities = client.get("/api/system").json()["recognizers"]
        assert capabilities["whisper"]["available"]
        assert not capabilities["qwen"]["available"]
        response = client.post(
            f"/api/projects/{record['id']}/analyze", json={"quality": "qwen", "offline": True}
        )
        assert response.status_code == 503
        assert response.json()["detail"] == runtime.QWEN_HELP
        folder = tmp_path / record["id"]
        assert read_json(folder / "job.json") == record
        assert not (folder / "result").exists()
        assert not (folder / "revisions").exists()
        assert app.state.manager.active_id is None
        assert app.state.manager.thread is None
