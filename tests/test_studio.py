import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from music_studio.io import sha256, write_json
from music_studio.studio import dsp
from music_studio.studio.models import Fade, Gain, Mix, Normalize, PreviewRequest, Reverse, Trim
from music_studio.studio.service import StudioError, StudioService
from music_studio.ui.server import create_app


def wav(path, data, rate=44100):
    sf.write(path, data, rate, subtype="FLOAT")
    return path


@pytest.fixture
def project(tmp_path):
    key = "1234567890abcdef"
    folder = tmp_path / key
    (folder / "input").mkdir(parents=True)
    t = np.arange(88200) / 44100
    signal = np.column_stack(
        [0.2 * np.sin(2 * np.pi * 220 * t), 0.15 * np.cos(2 * np.pi * 330 * t)]
    )
    source = wav(folder / "input/original.wav", signal)
    write_json(
        folder / "job.json",
        {
            "id": key,
            "title": "Test",
            "status": "ready",
            "created_at": 1,
            "filename": "original.wav",
        },
    )
    return StudioService(tmp_path), key, source


def test_sample_exact_operations_and_block_boundary(tmp_path):
    data = np.arange(dsp.BLOCK + 17, dtype=np.float32) / (dsp.BLOCK * 4)
    data = np.column_stack([data, -data])
    source = wav(tmp_path / "in.wav", data)
    before = sha256(source)
    out = tmp_path / "out.wav"
    dsp.process(source, out, Reverse(), {})
    np.testing.assert_array_equal(sf.read(out, dtype="float32")[0], data[::-1])
    dsp.process(source, out, Trim(start=13 / 44100, end=1003 / 44100), {})
    np.testing.assert_array_equal(sf.read(out, dtype="float32")[0], data[13:1003])
    dsp.process(source, out, Gain(db=-6.020599913), {})
    np.testing.assert_allclose(sf.read(out)[0], data / 2, atol=1e-8)
    dsp.process(source, out, Fade(in_seconds=0.1, out_seconds=0.1), {})
    rendered = sf.read(out)[0]
    np.testing.assert_array_equal(rendered[[0, -1]], np.zeros((2, 2)))
    np.testing.assert_array_equal(rendered[4410:-4410], data[4410:-4410])
    assert sha256(source) == before
    with pytest.raises(ValueError, match="overwrite"):
        dsp.process(source, source, Reverse(), {})
    with pytest.raises(ValueError, match="within"):
        dsp.process(source, out, Trim(start=0, end=30), {})


def test_normalize_silence_mix_and_integer_export(tmp_path):
    data = np.full((5000, 2), 0.25, dtype=np.float32)
    source = wav(tmp_path / "in.wav", data)
    out = tmp_path / "out.wav"
    dsp.process(source, out, Normalize(peak_dbfs=-1), {})
    assert dsp.inspect_audio(out)["peak_dbfs"] == pytest.approx(-1, abs=1e-5)
    silent = wav(tmp_path / "silent.wav", np.zeros_like(data))
    dsp.process(silent, out, Normalize(), {})
    assert dsp.inspect_audio(out)["peak"] == 0
    second = wav(tmp_path / "second.wav", data * 2)
    dsp.process(
        source,
        out,
        Mix(tracks=[{"asset": "a"}, {"asset": "b"}]),
        {
            "a": source,
            "b": second,
        },
    )
    np.testing.assert_array_equal(sf.read(out)[0], data * 3)
    dsp.process(out, tmp_path / "hot.wav", Gain(db=12), {})
    with pytest.raises(ValueError, match="full scale"):
        dsp.export_audio(tmp_path / "hot.wav", tmp_path / "clipped.wav")
    dsp.export_audio(out, tmp_path / "24.wav", "PCM_24")
    assert sf.info(tmp_path / "24.wav").subtype == "PCM_24"
    np.testing.assert_allclose(sf.read(tmp_path / "24.wav")[0], data * 3, atol=2e-7)


def test_preview_adopt_undo_restart_export_and_events(project):
    service, key, original = project
    digest = sha256(original)
    assert service.session(key)["revision"] == 0
    request = PreviewRequest(revision=0, operations=[{"type": "trim", "start": 0.2, "end": 1.2}])
    preview = service.preview(key, request, actor="mcp")
    assert preview["audio"]["frames"] == 44100
    assert service.session(key)["active"] == "source"
    active = service.adopt(key, preview["id"], 0, actor="codex")
    assert active["revision"] == 1
    restarted = StudioService(service.root)
    assert restarted.session(key)["active"] == f"candidate:{preview['id']}"
    undone = restarted.history(key, 1, "undo")
    assert undone["active"] == "source" and undone["revision"] == 2
    redone = service.history(key, 2, "redo")
    assert redone["active"] == active["active"] and redone["revision"] == 3
    exported = service.export(key, 3)
    np.testing.assert_allclose(
        sf.read(exported["path"])[0], sf.read(service.asset_path(key))[0], atol=2e-7
    )
    assert exported["revision"] == 3 and exported["asset"] == active["active"]
    events = service.events(key)
    assert [e["actor"] for e in events[:3]] == ["mcp", "mcp", "codex"]
    assert [e["kind"] for e in events] == [
        "preview.started",
        "preview.ready",
        "preview.adopted",
        "history.undo",
        "history.redo",
        "audio.exported",
    ]
    assert service.events(key, events[-1]["seq"]) == []
    assert sha256(original) == digest


def test_revision_conflict_between_independent_clients(project):
    service, key, _ = project
    candidate = service.preview(
        key, PreviewRequest(revision=0, operations=[{"type": "gain", "db": -3}])
    )

    def adopt(_):
        try:
            return StudioService(service.root).adopt(key, candidate["id"], 0)["revision"]
        except StudioError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(adopt, range(2))) == [1, 409]
    with pytest.raises(StudioError) as stale:
        service.export(key, 0)
    assert stale.value.status == 409


def test_failed_preview_does_not_modify_session_and_paths_are_scoped(project, tmp_path):
    service, key, _ = project
    with pytest.raises(ValueError):
        service.preview(
            key, PreviewRequest(revision=0, operations=[{"type": "trim", "start": 0, "end": 10}])
        )
    assert service.session(key)["revision"] == 0
    assert service.session(key)["candidates"][0]["status"] == "failed"
    with pytest.raises(StudioError):
        service.asset_path(key, "../../original.wav")
    with pytest.raises(StudioError):
        service.safe_file(service.project_dir(key), "../../elsewhere.wav")
    # Windows may require developer mode for symlinks; test containment where available.
    other = tmp_path / "outside"
    other.mkdir()
    evil_key = "abcdef1234567890"
    evil = tmp_path / evil_key
    evil.mkdir()
    write_json(evil / "job.json", {"filename": "original.wav"})
    try:
        (evil / ".studio").symlink_to(other, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(StudioError, match="working directory"):
        service.session(evil_key)


def test_http_edit_without_analysis_and_range_playback(tmp_path):
    data = io.BytesIO()
    sf.write(data, np.full((44100, 2), 0.1), 44100, format="WAV")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        key = client.post("/api/projects", files={"file": ("audio.wav", data.getvalue())}).json()[
            "id"
        ]
        prefix = f"/api/projects/{key}/studio"
        assert client.get(prefix).json()["audio"]["duration"] == 1
        preview = client.post(
            prefix + "/preview",
            json={
                "revision": 0,
                "operations": [
                    {"type": "gain", "db": -3},
                    {"type": "fade", "out_seconds": 0.1},
                ],
            },
        )
        assert preview.status_code == 201
        candidate = preview.json()["id"]
        assert client.get(prefix).json()["active"] == "source"
        response = client.get(
            prefix + f"/assets/candidate:{candidate}", headers={"Range": "bytes=0-43"}
        )
        assert response.status_code == 206 and response.content[:4] == b"RIFF"
        assert (
            client.post(prefix + "/adopt", json={"revision": 0, "candidate": candidate}).status_code
            == 200
        )
        assert client.post(prefix + "/export", json={"revision": 0}).status_code == 409
        export = client.post(prefix + "/export", json={"revision": 1})
        assert export.status_code == 201
        assert client.get(export.json()["url"]).content[:4] == b"RIFF"
        assert client.get(prefix + "/recipe/" + candidate).json()["operations"][0]["type"] == "gain"
        bad = client.post(
            prefix + "/preview",
            json={"revision": 1, "operations": [{"type": "trim", "start": 0, "end": 4}]},
        )
        assert bad.status_code == 422
        assert client.get(f"/api/projects/{key}").json()["status"] == "ready"
