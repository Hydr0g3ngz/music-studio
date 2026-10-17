import pytest
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

    def unexpected_analysis(*args, **kwargs):
        raise AssertionError("An unsupported bundled option must never start analysis")

    app = create_app(tmp_path, analyzer=unexpected_analysis)
    record, _ = app.state.manager.create("test.wav")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post(f"/api/projects/{record['id']}/analyze", json={"device": "cuda"})
        assert response.status_code == 422
        assert app.state.manager.thread is None
        response = client.post(f"/api/projects/{record['id']}/analyze", json={"quality": "text"})
        assert response.status_code == 422
        assert app.state.manager.thread is None


@pytest.mark.parametrize("available,expected", [(True, "cuda"), (False, "cpu")])
def test_gpu_installer_auto_resolves_actual_runtime(tmp_path, monkeypatch, available, expected):
    import threading

    from music_studio.config import Settings
    from music_studio.ui import server

    monkeypatch.setenv("MUSIC_STUDIO_BUNDLED_PROFILE", "cuda-small")
    monkeypatch.setattr(server, "acceleration_status", lambda: {"cuda_available": available})
    captured = []
    done = threading.Event()

    def capture(source, output, settings, **kwargs):
        captured.append(settings.device)
        done.set()
        raise RuntimeError("stop after capturing the effective analysis device")

    app = create_app(tmp_path, Settings(device="auto"), analyzer=capture)
    record, _ = app.state.manager.create("test.wav")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        data = client.get("/api/system").json()
        assert data["defaults"]["device"] == "auto"
        assert data["acceleration"]["cuda_available"] == available
        response = client.post(f"/api/projects/{record['id']}/analyze", json={"device": "auto"})
        assert response.status_code == 202
        assert done.wait(3)
        assert captured == [expected]
    app.state.manager.thread.join(timeout=3)


def test_gpu_installer_rejects_failed_cuda_without_writing_job(tmp_path, monkeypatch):
    from music_studio.io import read_json
    from music_studio.ui import server

    monkeypatch.setenv("MUSIC_STUDIO_BUNDLED_PROFILE", "cuda-small")
    monkeypatch.setattr(server, "acceleration_status", lambda: {"cuda_available": False})

    def unexpected_analysis(*args, **kwargs):
        raise AssertionError("An unavailable GPU or model must never start analysis")

    app = create_app(tmp_path, analyzer=unexpected_analysis)
    record, _ = app.state.manager.create("test.wav")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for options in ({"device": "cuda"}, {"quality": "text"}, {"alignment": "anchors_dual"}):
            response = client.post(f"/api/projects/{record['id']}/analyze", json=options)
            assert response.status_code == 422
            assert read_json(tmp_path / record["id"] / "job.json") == record
            assert app.state.manager.thread is None
