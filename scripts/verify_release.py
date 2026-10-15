"""Run from an isolated venv against the installed wheel, without neural models.

Install the wheel with [ui] plus httpx, then invoke this script from outside the
source checkout. Assertions cover the packaged UI, demo, exports and recovery.
"""

import argparse
import importlib.util
import tempfile
from pathlib import Path

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
            response = client.patch(f"{prefix}/lyrics", json={
                "version": "original", "revision": 0, "changes": {line["id"]: "Release smoke test"},
            })
            assert response.status_code == 200
            assert "Release smoke test" in client.get(f"{prefix}/assets/lrc").text
            assert client.delete(prefix).status_code == 200
            assert client.get(prefix).status_code == 404
            assert client.post(f"/api/trash/{job['id']}/restore").status_code == 200
            assert client.get(f"{prefix}/result").json()["lyrics"]["segments"][0][
                "text"
            ] == "Release smoke test"
            if no_models:
                error = client.post(f"{prefix}/analyze", json={})
                assert error.status_code == 503 and "setup.ps1" in error.json()["detail"]
    print(f"PASS: installed wheel {music_studio.__version__}; UI/demo/assets/edits/export/trash")
    print(f"PASS: credited demo hashes; no-model runtime={no_models}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-models", action="store_true")
    args = parser.parse_args()
    verify(no_models=args.no_models)
