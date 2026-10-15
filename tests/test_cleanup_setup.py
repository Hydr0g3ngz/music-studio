import io

import numpy as np
import pytest
from fastapi.testclient import TestClient

from music_studio.config import Settings
from music_studio.io import read_json, sha256
from music_studio.studio import cleanup
from music_studio.studio.registry import ModelRegistry
from music_studio.ui.server import create_app


def test_failed_download_cannot_replace_a_cache_or_choose_an_arbitrary_model(tmp_path, monkeypatch):
    model = cleanup.model_path(tmp_path)
    model.parent.mkdir()
    model.write_bytes(b"existing incomplete cache")
    original = sha256(model)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(b"bad model"))
    with pytest.raises(ValueError, match="checksum"):
        cleanup.download(tmp_path)
    assert sha256(model) == original
    assert not list(model.parent.glob("*.part"))
    with pytest.raises(ValueError, match="Unknown fixed"):
        cleanup.download(tmp_path, "../../user-file")


def test_model_setup_is_fixed_explicit_and_origin_guarded(tmp_path, monkeypatch):
    downloaded = []

    def check(self, model, **kwargs):
        return self.describe(model, {"state": "verified", "weights": bool(downloaded)})

    monkeypatch.setattr(ModelRegistry, "check", check)
    monkeypatch.setattr(cleanup, "download", lambda root, model: downloaded.append((root, model)))
    model_root = tmp_path / "fixed-model-cache"
    with TestClient(
        create_app(tmp_path / "workspace", Settings(model_dir=str(model_root))),
        base_url="http://127.0.0.1",
    ) as client:
        assert client.get("/api/studio/models").status_code == 200
        assert downloaded == []
        route = "/api/studio/models/dpdfnet2-48k/install"
        assert (
            client.post(route, headers={"Origin": "https://unrelated.example"}).status_code == 403
        )
        assert client.post(route, json={"model_dir": "elsewhere"}).status_code == 422
        assert client.post("/api/studio/models/whisper-small/install").status_code == 404
        assert downloaded == []
        assert client.post(route).status_code == 200
        assert downloaded == [(str(model_root.resolve()), "dpdfnet2-48k")]


def test_licensed_speech_starter_is_an_editable_import_without_automatic_analysis(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/studio/demo/speech")
        assert response.status_code == 201
        job = response.json()
        assert job["status"] == "ready" and not job["has_result"]
        assert job["attribution"]["license"] == "CC BY 4.0"
        source = tmp_path / job["id"] / "input" / job["filename"]
        original = sha256(source)
        state = client.get(f"/api/projects/{job['id']}/studio").json()
        assert state["audio"]["duration"] == pytest.approx(23.111625, abs=1 / 44100)
        assert state["audio"]["sample_rate"] == 44100 and state["audio"]["channels"] == 2
        assert state["revision"] == 0
        assert sha256(source) == original
        assert not (source.parent.parent / "result").exists()
        manifest = read_json(source.parent.parent / ".studio/source.json")
        assert manifest["file"]
        assert np.isfinite(state["audio"]["peak"])
