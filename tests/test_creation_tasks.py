import json
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from filelock import FileLock

from music_studio.io import read_json, write_json
from music_studio.studio import creation
from music_studio.studio.process import TaskStopped
from music_studio.ui.server import create_app


def wait_for(client, prefix, states):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        task = client.get(prefix + "/generations").json()[0]
        if task["status"] in states:
            return task
        time.sleep(0.025)
    pytest.fail(f"Task stayed {task['status']}: {task}")


@pytest.fixture
def fake_runtime(monkeypatch, tmp_path):
    config = {
        "python": sys.executable,
        "source": str(tmp_path / "source"),
        "checkpoints": str(tmp_path / "weights"),
        "source_revision": creation.SOURCE_REVISION,
        "model_revision": creation.MODEL_REVISION,
    }
    monkeypatch.setattr(creation, "runtime", lambda: config)
    return config


def completed_worker(arguments, log_path, environment, **kwargs):
    request = read_json(Path(arguments[-1]))
    output = log_path.parent / "output"
    output.mkdir()
    # A fixture waveform, never presented as actual model inference.
    samples = np.sin(np.arange(48000) * 2 * np.pi * 220 / 48000) * 0.1
    sf.write(output / "generated.wav", np.column_stack([samples, samples]), 48000)
    write_json(output / "result.json", {"file": "generated.wav", "metrics": {"test": True}})
    assert environment["HF_HUB_OFFLINE"] == "1"
    assert request["parameters"]["seed"] == 42
    assert request["owner_pid"] > 0
    return 0


def test_generation_stays_a_draft_until_adopt_and_keeps_provenance(
    fake_runtime, monkeypatch, tmp_path
):
    monkeypatch.setattr(creation, "run_owned", completed_worker)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        state = client.post("/api/workstation/projects", json={"title": "Music"}).json()
        prefix = f"/api/workstation/projects/{state['id']}"
        submitted = client.post(
            prefix + "/generations", json={"revision": 0, "prompt": "Soft jazz piano"}
        )
        assert submitted.status_code == 202, submitted.text
        assert "runtime" not in submitted.json()
        task = wait_for(client, prefix, {"complete", "failed"})
        assert task["status"] == "complete", task
        assert client.get(prefix).json() == state
        assert task["audio"]["sample_rate"] == 44100
        assert task["audio"]["channels"] == 2
        audio_url = f"{prefix}/generations/{task['id']}/audio"
        assert client.get(audio_url).status_code == 200
        adopted = client.post(
            f"{prefix}/generations/{task['id']}/adopt", json={"revision": 0, "at": 1.5}
        )
        assert adopted.status_code == 200, adopted.text
        updated = adopted.json()
        clip = updated["content"]["tracks"][0]["clips"][0]
        assert clip["start"] == 1.5
        assert clip["origin"]["sha256"] == task["sha256"]
        assert creation.MODEL_REVISION in clip["origin"]["details"]
        assert (
            client.post(
                f"{prefix}/generations/{task['id']}/adopt", json={"revision": 0}
            ).status_code
            == 409
        )
        undone = client.post(prefix + "/history/undo", json={"revision": 1}).json()
        assert undone["content"]["tracks"] == []
        assert client.get(audio_url).status_code == 200
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get(prefix + "/generations").json()[0]["status"] == "complete"


def test_queued_cancel_limits_and_restart_recovery(fake_runtime, tmp_path):
    lock = FileLock(str(tmp_path / ".studio-tasks.lock"), timeout=0)
    with lock, TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        state = client.post("/api/workstation/projects", json={}).json()
        prefix = f"/api/workstation/projects/{state['id']}"
        payload = {"revision": 0, "prompt": "Cinematic music"}
        for _ in range(5):
            assert client.post(prefix + "/generations", json=payload).status_code == 202
        assert client.post(prefix + "/generations", json=payload).status_code == 409
        task = client.get(prefix + "/generations").json()[0]
        result = client.post(f"{prefix}/generations/{task['id']}/cancel", json={})
        assert result.json()["status"] == "cancelled"
        assert client.get(f"{prefix}/generations/{task['id']}/audio").status_code == 409
        # Simulate a process which stopped while a task was running.
        studio = client.app.state.studio
        with studio.connection() as db:
            db.execute("UPDATE creation_tasks SET status='running' WHERE status='queued'")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        recovered = wait_for(client, prefix, {"cancelled", "interrupted"})
        assert recovered["status"] == "cancelled"
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            states = {t["status"] for t in client.get(prefix + "/generations").json()}
            if states == {"cancelled", "interrupted"}:
                break
            time.sleep(0.025)
        assert states == {"cancelled", "interrupted"}


def test_running_cancel_stops_worker_and_never_changes_arrangement(
    fake_runtime, monkeypatch, tmp_path
):
    entered = threading.Event()

    def blocking_worker(*args, cancelled, **kwargs):
        entered.set()
        while not cancelled():
            time.sleep(0.01)
        raise TaskStopped("cancelled")

    monkeypatch.setattr(creation, "run_owned", blocking_worker)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        state = client.post("/api/workstation/projects", json={}).json()
        prefix = f"/api/workstation/projects/{state['id']}"
        task = client.post(
            prefix + "/generations", json={"revision": 0, "prompt": "Jazz trio"}
        ).json()
        assert entered.wait(5)
        client.post(f"{prefix}/generations/{task['id']}/cancel", json={})
        assert wait_for(client, prefix, {"cancelled"})["status"] == "cancelled"
        assert client.get(prefix).json() == state


def test_runtime_errors_and_generation_validation(monkeypatch, tmp_path):
    config = tmp_path / "runtime.json"
    monkeypatch.setenv("MUSIC_STUDIO_ACE_CONFIG", str(config))
    with TestClient(create_app(tmp_path / "work"), base_url="http://127.0.0.1") as client:
        state = client.post("/api/workstation/projects", json={}).json()
        prefix = f"/api/workstation/projects/{state['id']}"
        assert not client.get("/api/workstation/generation/status").json()["available"]
        assert (
            client.post(
                prefix + "/generations", json={"revision": 0, "prompt": "Jazz piano"}
            ).status_code
            == 503
        )
        config.write_text(json.dumps({"source_revision": "wrong"}), encoding="utf-8")
        assert (
            client.post(
                prefix + "/generations", json={"revision": 0, "prompt": "Jazz piano"}
            ).status_code
            == 503
        )
        config.write_text("[]", encoding="utf-8")
        assert not client.get("/api/workstation/generation/status").json()["available"]
        assert (
            client.post(
                prefix + "/generations", json={"revision": 0, "prompt": "Jazz piano"}
            ).status_code
            == 503
        )
        for change in (
            {"duration": 300},
            {"seed": -1},
            {"prompt": "   "},
            {"instrumental": False},
            {"steps": 50},
        ):
            assert (
                client.post(
                    prefix + "/generations",
                    json={
                        "revision": 0,
                        "prompt": "Jazz piano",
                        **change,
                    },
                ).status_code
                == 422
            )


def test_failed_draft_keeps_resource_diagnostics_and_original_project(
    fake_runtime, monkeypatch, tmp_path
):
    def failing_worker(arguments, log_path, environment, **kwargs):
        output = log_path.parent / "output"
        output.mkdir()
        log_path.write_text("Fixture: CUDA out of memory", encoding="utf-8")
        write_json(
            output / "failure.json",
            {
                "metrics": {
                    "total_seconds": 2.5,
                    "peak_allocated_mib": 3500,
                }
            },
        )
        return 1

    monkeypatch.setattr(creation, "run_owned", failing_worker)
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        state = client.post("/api/workstation/projects", json={}).json()
        prefix = f"/api/workstation/projects/{state['id']}"
        assert (
            client.post(
                prefix + "/generations",
                json={
                    "revision": 0,
                    "prompt": "Jazz piano",
                },
            ).status_code
            == 202
        )
        task = wait_for(client, prefix, {"failed"})
        assert task["metrics"]["peak_allocated_mib"] == 3500
        assert "out of memory" in task["error"]
        assert task["worker_sha256"]
        assert client.get(prefix).json() == state
