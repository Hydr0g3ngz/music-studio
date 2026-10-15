"""The release must offer a usable, credited demo without models or downloads."""

from pathlib import Path

import soundfile as sf
from fastapi.testclient import TestClient

from music_studio.io import read_json, sha256
from music_studio.schema import Project
from music_studio.ui.server import create_app


def test_bundled_demo_is_offline_editable_and_recoverable(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The bundled demo must not access the network or run inference")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    app = create_app(tmp_path, analyzer=forbidden)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/demo")
        assert response.status_code == 201
        job = response.json()
        assert job["status"] == "complete" and job["has_result"]
        assert job["precomputed_demo"] and job["attribution"]["license"] == "CC BY 3.0"
        project_id = job["id"]
        result = client.get(f"/api/projects/{project_id}/result").json()
        project = Project.model_validate(result)
        assert project.audio.duration == 45 and len(project.lyrics.segments) >= 4
        for name, relative in project.assets.items():
            assert client.get(f"/api/projects/{project_id}/assets/{name}").status_code == 200
            if name in ("source", "vocals", "instrumental"):
                info = sf.info(tmp_path / project_id / "result" / relative)
                assert info.frames == project.audio.samples
        line = project.lyrics.segments[0]
        saved = client.patch(f"/api/projects/{project_id}/lyrics", json={
            "version": "original", "revision": 0, "changes": {line.id: "Corrected demo lyrics"},
        })
        assert saved.status_code == 200
        assert "Corrected demo lyrics" in client.get(
            f"/api/projects/{project_id}/assets/lrc"
        ).text
        assert client.delete(f"/api/projects/{project_id}").status_code == 200
        assert client.post(f"/api/trash/{project_id}/restore").status_code == 200
        assert client.get(f"/api/projects/{project_id}/result").json()[
            "lyrics"
        ]["segments"][0]["text"] == "Corrected demo lyrics"
    # Editing the workspace copy cannot modify the package's original fixture.
    bundled = Path(__file__).parents[1] / "src/music_studio/ui/demo"
    manifest = read_json(bundled / "manifest.json")
    assert all(sha256(bundled / name) == digest for name, digest in manifest["files"].items())


def test_missing_inference_has_actionable_error_without_starting_a_job(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        project_id = client.post("/api/demo").json()["id"]
        monkeypatch.setattr("music_studio.ui.server.importlib.util.find_spec", lambda _: None)
        response = client.post(f"/api/projects/{project_id}/analyze", json={})
        assert response.status_code == 503
        assert "setup.ps1 -Mode full" in response.json()["detail"]
        assert client.get(f"/api/projects/{project_id}").json()["status"] == "complete"
