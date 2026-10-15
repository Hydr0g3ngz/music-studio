import io
import threading
import time
from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from music_studio.config import Settings
from music_studio.export import export_project
from music_studio.io import read_json, sha256, write_json
from music_studio.pipeline import AnalysisCancelled
from music_studio.schema import (
    AudioInfo,
    Harmony,
    LyricLine,
    Lyrics,
    Melody,
    Note,
    Project,
    Rhythm,
    Word,
)
from music_studio.ui.server import create_app


def audio_bytes():
    data = io.BytesIO()
    t = np.arange(44100) / 44100
    sf.write(data, np.sin(2 * np.pi * 440 * t) * 0.2, 44100, format="WAV")
    return data.getvalue()


def finished_analysis(source, output, settings, **kwargs):
    (output / "audio").mkdir(parents=True)
    signal, rate = sf.read(source)
    for name in ("source", "vocals", "instrumental"):
        sf.write(output / f"audio/{name}.wav", np.column_stack([signal, signal]), rate)
    assets = {name: f"audio/{name}.wav" for name in ("source", "vocals", "instrumental")}
    assets.update(
        pitch="analysis/pitch.json",
        midi="exports/melody.mid",
        lrc="exports/lyrics.lrc",
        srt="exports/lyrics.srt",
    )
    project = Project(
        audio=AudioInfo(
            source_name=source.name,
            source_sha256=sha256(source),
            sample_rate=rate,
            samples=len(signal),
            channels=2,
            duration=len(signal) / rate,
        ),
        lyrics=Lyrics(
            language="en",
            timing_method="test",
            segments=[
                LyricLine(
                    id="l0000",
                    text="wrong word",
                    start=0.1,
                    end=0.9,
                    words=[
                        Word(id="w0000", text="wrong", start=0.1, end=0.4),
                        Word(id="w0001", text="word", start=0.5, end=0.9),
                    ],
                )
            ],
        ),
        melody=Melody(
            backend="test",
            notes=[
                Note(id="n0000", start=0.1, end=0.4, pitch=69, score=0.8, lyric_word_ids=["w0000"])
            ],
        ),
        rhythm=Rhythm(backend="test", beats=[0.25, 0.75], bpm=120),
        harmony=Harmony(backend="test", chords=[]),
        assets=assets,
        settings=settings.model_dump(),
        stages={},
    )
    write_json(output / "analysis/pitch.json", {"times": [], "frequency_hz": [], "periodicity": []})
    export_project(project, output)
    write_json(output / "project.json", project.model_dump())
    write_json(output / "run.json", {"status": "complete", "stages": {}})
    return project


def wait_status(client, project_id, status):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        record = client.get(f"/api/projects/{project_id}").json()
        if record["status"] == status:
            return record
        time.sleep(0.02)
    pytest.fail(f"Project did not reach {status}; last state: {record}")


def upload(client, filename="测试 歌曲.wav"):
    response = client.post("/api/projects", files={"file": (filename, audio_bytes(), "audio/wav")})
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_analyze_stream_and_restore_history(tmp_path):
    app = create_app(tmp_path, Settings(), analyzer=finished_analysis)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/").status_code == 200
        assert client.get("/app.js").status_code == 200
        assert client.get("/playback.js").status_code == 200
        project_id = upload(client)
        assert client.get(f"/api/projects/{project_id}/result").status_code == 409
        assert client.post(f"/api/projects/{project_id}/analyze", json={}).status_code == 202
        record = wait_status(client, project_id, "complete")
        assert record["duration"] == 1
        result = client.get(f"/api/projects/{project_id}/result").json()
        assert result["audio"]["samples"] == 44100
        waves = client.get(f"/api/projects/{project_id}/waveforms").json()
        assert 1 <= len(waves["source"]) <= 1800
        assert max(waves["source"]) == pytest.approx(0.2, abs=0.001)
        response = client.get(
            f"/api/projects/{project_id}/assets/source", headers={"Range": "bytes=0-43"}
        )
        assert response.status_code == 206
        assert response.content[:4] == b"RIFF"
        midi = client.get(f"/api/projects/{project_id}/assets/midi")
        assert midi.content[:4] == b"MThd"
        assert "attachment" in midi.headers["content-disposition"]
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get("/api/projects").json()[0]["status"] == "complete"


def test_single_analysis_and_cancel(tmp_path):
    entered = threading.Event()

    def slow_analysis(source, output, settings, *, cancel_event, **kwargs):
        entered.set()
        assert cancel_event.wait(timeout=3)
        raise AnalysisCancelled("Stopped by user")

    app = create_app(tmp_path, analyzer=slow_analysis)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        first, second = upload(client), upload(client)
        assert client.post(f"/api/projects/{first}/analyze", json={}).status_code == 202
        assert entered.wait(1)
        assert client.post(f"/api/projects/{second}/analyze", json={}).status_code == 409
        assert client.delete(f"/api/projects/{first}").status_code == 409
        assert (
            client.patch(
                f"/api/projects/{first}", json={"title": "renamed during analysis"}
            ).status_code
            == 200
        )
        assert client.post(f"/api/projects/{first}/cancel").status_code == 200
        wait_status(client, first, "cancelled")
        assert client.get(f"/api/projects/{first}").json()["title"] == "renamed during analysis"
        # The next request must acquire the released slot. Reading active_id directly
        # races with the final status write, which is protected by the manager lock.
        assert client.post(f"/api/projects/{second}/analyze", json={}).status_code == 202
        assert client.post(f"/api/projects/{second}/cancel").status_code == 200
        wait_status(client, second, "cancelled")


def test_invalid_files_and_cross_origin_requests(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.post("/api/projects", files={"file": ("bad.exe", b"x")}).status_code == 400
        assert client.post("/api/projects", files={"file": ("empty.wav", b"")}).status_code == 400
        count = len(client.get("/api/projects").json())
        response = client.post(
            "/api/projects",
            files={"file": ("a.wav", audio_bytes())},
            headers={"Origin": "https://unrelated.example"},
        )
        assert response.status_code == 403
        assert len(client.get("/api/projects").json()) == count
        assert client.get("/api/projects/unknown/result").status_code == 404


def test_project_assets_cannot_escape_project_directory(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        project_id = upload(client)
        client.post(f"/api/projects/{project_id}/analyze", json={})
        wait_status(client, project_id, "complete")
        path = Path(tmp_path / project_id / "result/project.json")
        project = read_json(path)
        project["assets"]["source"] = "../../outside.wav"
        write_json(path, project)
        assert client.get(f"/api/projects/{project_id}/assets/source").status_code == 404


def test_delete_and_restore_preserve_project_and_survive_restart(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier = upload(client)
        client.post(f"/api/projects/{identifier}/analyze", json={})
        wait_status(client, identifier, "complete")
        original = client.get(f"/api/projects/{identifier}/assets/midi").content
        assert (
            client.patch(f"/api/projects/{identifier}", json={"title": "  我的歌  "}).json()[
                "title"
            ]
            == "我的歌"
        )
        assert client.patch(f"/api/projects/{identifier}", json={"title": "   "}).status_code == 422
        assert client.delete(f"/api/projects/{identifier}").json()["status"] == "trashed"
        assert client.get("/api/projects").json() == []
        assert client.get(f"/api/projects/{identifier}/assets/midi").status_code == 404
        assert client.get("/api/trash").json()[0]["title"] == "我的歌"
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.post(f"/api/trash/{identifier}/restore").json()["status"] == "complete"
        assert client.get(f"/api/projects/{identifier}/assets/midi").content == original
        assert client.get("/api/trash").json() == []
        assert client.post(f"/api/trash/{identifier}/restore").status_code == 404
        assert client.delete("/api/projects/invalid").status_code == 404


def test_lyric_corrections_export_and_restore_without_mutating_recognition(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier = upload(client)
        prefix = f"/api/projects/{identifier}"
        assert (
            client.patch(
                prefix + "/lyrics", json={"revision": 0, "changes": {"l0000": "x"}}
            ).status_code
            == 409
        )
        client.post(prefix + "/analyze", json={})
        wait_status(client, identifier, "complete")
        raw = sha256(tmp_path / identifier / "result/project.json")
        body = {"revision": 0, "changes": {"l0000": "正确歌词 & <test>"}}
        assert client.patch(prefix + "/lyrics", json=body).json()["revision"] == 1
        result = Project.model_validate(client.get(prefix + "/result").json())
        assert result.lyrics.segments[0].text == "正确歌词 & <test>"
        assert result.lyrics.segments[0].start == 0.1
        assert result.lyrics.segments[0].words == []
        assert result.melody.notes[0].lyric_word_ids == []
        assert "正确歌词 & <test>" in client.get(prefix + "/assets/lrc").content.decode("utf-8")
        assert "00:00:00,100 --> 00:00:00,900" in client.get(prefix + "/assets/srt").text
        assert (
            client.get(prefix + "/assets/project").json()["lyrics"]["segments"][0]["text"]
            == "正确歌词 & <test>"
        )
        midi = mido.MidiFile(
            file=io.BytesIO(client.get(prefix + "/assets/midi").content), charset="utf-8"
        )
        assert [message.text for message in midi if message.type == "lyrics"] == [
            "正确歌词 & <test>"
        ]
        assert sha256(tmp_path / identifier / "result/project.json") == raw
        assert client.patch(prefix + "/lyrics", json=body).status_code == 409
        assert (
            client.patch(
                prefix + "/lyrics", json={"revision": 1, "changes": {"bad": "x"}}
            ).status_code
            == 422
        )
        assert (
            client.patch(
                prefix + "/lyrics", json={"revision": 1, "changes": {"l0000": "x\ny"}}
            ).status_code
            == 422
        )
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert client.get(prefix + "/lyrics").json()["revision"] == 1
        client.patch(prefix + "/lyrics", json={"revision": 1, "changes": {"l0000": None}})
        result = client.get(prefix + "/result").json()
        assert result["lyrics"]["segments"][0]["text"] == "wrong word"
        assert len(result["lyrics"]["segments"][0]["words"]) == 2
        assert result["melody"]["notes"][0]["lyric_word_ids"] == ["w0000"]


def test_quality_modes_resolve_their_own_model_revision(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        for quality, model, revision in (
            ("text", "large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"),
            ("balanced", "small", "536b0662742c02347bc0e980a01041f333bce120"),
        ):
            identifier = upload(client)
            assert (
                client.post(
                    f"/api/projects/{identifier}/analyze", json={"quality": quality}
                ).status_code
                == 202
            )
            record = wait_status(client, identifier, "complete")
            assert record["settings"]["asr_model"] == model
            assert record["settings"]["asr_revision"] == revision
