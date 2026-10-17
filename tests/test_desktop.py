from fastapi.testclient import TestClient

from music_studio.desktop import identity, probe
from music_studio.ui.server import create_app


def test_independent_identity_and_reject_foreign_server(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        value = client.get("/api/instance").json()
        assert value == {"product": "music-studio", "workspace": identity(tmp_path)}
        assert identity(tmp_path) != identity(tmp_path / "other")
    for url in ("https://127.0.0.1:8765", "http://example.com", "http://127.0.0.1:8765/x",
                "http://user@127.0.0.1:8765", "file:///tmp/music"):
        assert not probe(url, tmp_path)


def test_bundled_profile_does_not_change_source_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSIC_STUDIO_BUNDLED_PROFILE", "cpu-small")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/system").json()["distribution"] == "cpu-small"


def test_bundled_profile_rejects_unavailable_device_before_start(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSIC_STUDIO_BUNDLED_PROFILE", "cpu-small")
    app = create_app(tmp_path)
    record, _ = app.state.manager.create("test.wav")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(f"/api/projects/{record['id']}/analyze", json={"device": "cuda"})
        assert response.status_code == 422
        assert app.state.manager.thread is None
        response = client.post(f"/api/projects/{record['id']}/analyze", json={"quality": "text"})
        assert response.status_code == 422
        assert app.state.manager.thread is None
