"""Run from an isolated venv against the installed wheel, without neural models.

Install the wheel with [ui,audio,agent] plus httpx. Assertions cover the packaged
classic and Next UI, real audio edits, the isolated local queue, exports and recovery.
"""

import argparse
import importlib.util
import io
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

import music_studio
from music_studio.io import read_json, sha256
from music_studio.ui.server import create_app


def verify(*, no_models=False):
    package = Path(music_studio.__file__).resolve().parent
    if no_models:
        for name in ("torch", "demucs", "faster_whisper", "qwen_asr"):
            assert importlib.util.find_spec(name) is None, f"Expected no {name} in preview venv"
    assert "site-packages" in package.parts, "Verify the installed wheel, not an editable checkout"
    bundled = package / "ui/demo"
    manifest = read_json(bundled / "manifest.json")
    assert all(sha256(bundled / name) == digest for name, digest in manifest["files"].items())
    with tempfile.TemporaryDirectory(prefix="music-studio-release-") as temporary:
        with TestClient(create_app(Path(temporary)), base_url="http://127.0.0.1") as client:
            assert client.get("/").status_code == 200
            for asset in ("i18n.js", "app.js", "playback.js", "style.css", "workbench.css"):
                assert client.get(f"/{asset}").status_code == 200
            system = client.get("/api/system").json()
            if no_models:
                assert not system["inference_installed"]
            job = client.post("/api/demo").json()
            assert job["has_result"] and job["status"] == "complete"
            prefix = f"/api/projects/{job['id']}"
            project = client.get(f"{prefix}/result").json()
            assert project["audio"]["duration"] == 45
            assert client.get(f"{prefix}/waveforms").json()["source"]
            for name in project["assets"]:
                assert client.get(f"{prefix}/assets/{name}").status_code == 200
            line = project["lyrics"]["segments"][0]
            response = client.patch(
                f"{prefix}/lyrics",
                json={
                    "version": "original",
                    "revision": 0,
                    "changes": {line["id"]: "Release smoke test"},
                },
            )
            assert response.status_code == 200
            assert "Release smoke test" in client.get(f"{prefix}/assets/lrc").text
            assert client.delete(prefix).status_code == 200
            assert client.get(prefix).status_code == 404
            assert client.post(f"/api/trash/{job['id']}/restore").status_code == 200
            assert (
                client.get(f"{prefix}/result").json()["lyrics"]["segments"][0]["text"]
                == "Release smoke test"
            )
            if no_models:
                error = client.post(f"{prefix}/analyze", json={})
                assert error.status_code == 503 and "setup.ps1" in error.json()["detail"]
    print(f"PASS: installed wheel {music_studio.__version__}; UI/demo/assets/edits/export/trash")
    print(f"PASS: credited demo hashes; no-model runtime={no_models}")


def verify_next():
    with tempfile.TemporaryDirectory(prefix="music-studio-next-release-") as temporary:
        with TestClient(create_app(Path(temporary)), base_url="http://127.0.0.1") as client:
            assert client.get("/next.html").status_code == 200
            for asset in ("next.js", "next.css", "transport.js"):
                assert client.get("/" + asset).status_code == 200
            models = client.get("/api/studio/models").json()
            assert len(models) == 7 and all(m["health"]["state"] == "unchecked" for m in models)
            data = io.BytesIO()
            t = np.arange(88200) / 44100
            signal = np.column_stack([np.sin(t * np.pi * 440), np.cos(t * np.pi * 660)]) * 0.2
            sf.write(data, signal, 44100, format="WAV", subtype="PCM_24")
            uploaded = client.post(
                "/api/projects", files={"file": ("Unicode-音频.wav", data.getvalue())}
            )
            assert uploaded.status_code == 201
            project = uploaded.json()["id"]
            prefix = f"/api/projects/{project}/studio"
            state = client.get(prefix).json()
            assert state["audio"]["frames"] == 88200
            preview = client.post(
                prefix + "/preview",
                json={
                    "revision": 0,
                    "operations": [
                        {"type": "trim", "start": 0.25, "end": 1.25},
                        {"type": "gain", "db": -3},
                        {"type": "fade", "in_seconds": 0.05, "out_seconds": 0.05},
                    ],
                },
            )
            assert preview.status_code == 201, preview.text
            candidate = preview.json()["id"]
            assert (
                client.post(
                    prefix + "/adopt", json={"revision": 0, "candidate": candidate}
                ).status_code
                == 200
            )
            assert (
                client.post(prefix + "/history/undo", json={"revision": 1}).json()["active"]
                == "source"
            )
            assert (
                client.post(prefix + "/history/redo", json={"revision": 2}).json()["active"]
                == "candidate:" + candidate
            )
            exported = client.post(
                prefix + "/export", json={"revision": 3, "subtype": "PCM_24"}
            ).json()
            info = sf.info(io.BytesIO(client.get(exported["url"]).content))
            assert info.frames == 44100 and info.subtype == "PCM_24"
            queued = client.post(prefix + "/tasks", json={"revision": 3, "model": "inspect"})
            assert queued.status_code == 202, queued.text
            deadline = time.monotonic() + 30
            task = queued.json()
            while time.monotonic() < deadline:
                task = client.get(prefix + "/tasks").json()[0]
                if task["status"] in ("complete", "failed", "interrupted"):
                    break
                time.sleep(0.1)
            assert task["status"] == "complete", task
            artifact = task["artifacts"][0]["id"]
            assert client.get(prefix + "/artifacts/" + artifact).json()["frames"] == 44100
            assert client.get(prefix).json()["revision"] == 3
            assert client.delete(f"/api/projects/{project}").status_code == 200
            assert client.post(f"/api/trash/{project}/restore").status_code == 200
    print("PASS: Next installed UI/import/edit/undo/redo/WAV/isolated task/assets/trash")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-models", action="store_true")
    args = parser.parse_args()
    verify(no_models=args.no_models)
    verify_next()
