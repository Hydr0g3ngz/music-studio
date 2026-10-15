import threading
from pathlib import Path

from fastapi.testclient import TestClient
from test_ui import finished_analysis, upload, wait_status

from music_studio.export import export_project
from music_studio.io import read_json, sha256, write_json
from music_studio.pipeline import AnalysisCancelled
from music_studio.schema import Lyrics, Project
from music_studio.ui.revisions import link_file, update_lyrics
from music_studio.ui.server import create_app


def fake_update(base, output, settings, **kwargs):
    project = Project.model_validate(read_json(base / "project.json"))
    project.settings = settings.model_dump()
    if kwargs.get("supplied"):
        project.lyrics = kwargs["supplied"]
    else:
        project.lyrics.segments[0].text = "new recognition"
        project.lyrics.segments[0].words = []
    project.melody.notes[0].lyric_word_ids = []
    for relative in project.assets.values():
        if (base / relative).is_file():
            link_file(base / relative, output / relative)
    export_project(project, output)
    write_json(output / "project.json", project.model_dump())
    return project


def initial(client):
    identifier = upload(client)
    prefix = f"/api/projects/{identifier}"
    assert client.post(prefix + "/analyze", json={}).status_code == 202
    wait_status(client, identifier, "complete")
    return identifier, prefix


def test_review_is_persistent_version_bound_and_invalidated_by_edit(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        response = client.patch(
            prefix + "/review",
            json={"version": "original", "revision": 0, "line_id": "l0000", "reviewed": True},
        )
        assert response.status_code == 200
        assert client.get(prefix + "/lyrics").json()["review"]["counts"]["reviewed"] == 1
        assert (
            client.patch(
                prefix + "/review", json={"version": "original", "revision": 0, "line_id": "l0000"}
            ).status_code
            == 409
        )
        client.patch(
            prefix + "/lyrics",
            json={"version": "original", "revision": 1, "changes": {"l0000": "corrected"}},
        )
        assert client.get(prefix + "/lyrics").json()["review"]["counts"]["reviewed"] == 0
        assert client.get(prefix + "/lyrics").json()["review"]["counts"]["timing"] == 1


def test_candidate_requires_adoption_and_guards_newer_corrections(tmp_path, monkeypatch):
    monkeypatch.setattr("music_studio.ui.server.update_lyrics", fake_update)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)

        def candidate():
            revision = client.get(prefix + "/lyrics").json()["revision"]
            response = client.post(
                prefix + "/analyze",
                json={
                    "scope": "retry",
                    "candidate": True,
                    "base_version": "original",
                    "edit_revision": revision,
                    "line_id": "l0000",
                },
            )
            assert response.status_code == 202
            record = wait_status(client, identifier, "complete")
            assert record["current_version"] == "original"
            return record["candidate_version"]

        first = candidate()
        client.patch(
            prefix + "/lyrics", json={"revision": 0, "changes": {"l0000": "newer correction"}}
        )
        assert (
            client.post(
                prefix + "/versions/select", json={"version": first, "expected_current": "original"}
            ).status_code
            == 409
        )
        second = candidate()
        assert (
            client.post(
                prefix + "/versions/select",
                json={"version": second, "expected_current": "original"},
            ).status_code
            == 200
        )
        assert client.get(prefix).json()["current_version"] == second


def test_reanalysis_keeps_version_bound_corrections_and_history(tmp_path, monkeypatch):
    monkeypatch.setattr("music_studio.ui.server.update_lyrics", fake_update)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        raw = sha256(tmp_path / identifier / "result/project.json")
        client.patch(
            prefix + "/lyrics",
            json={
                "revision": 0,
                "version": "original",
                "changes": {"l0000": "user correction"},
            },
        )
        assert (
            client.post(
                prefix + "/analyze",
                json={
                    "scope": "lyrics",
                    "quality": "text",
                    "base_version": "original",
                },
            ).status_code
            == 202
        )
        record = wait_status(client, identifier, "complete")
        version = record["current_version"]
        assert version != "original"
        assert client.get(prefix + "/result").json()["lyrics"]["segments"][0]["text"] == (
            "new recognition"
        )
        assert client.get(prefix + "/lyrics").json()["changes"] == {}
        assert (
            client.get(prefix + "/result?version=original").json()["lyrics"]["segments"][0]["text"]
            == "user correction"
        )
        assert sha256(tmp_path / identifier / "result/project.json") == raw
        # The same line ID in a new recognition must not inherit an old editor's update.
        assert (
            client.patch(
                prefix + "/lyrics",
                json={
                    "revision": 1,
                    "version": "original",
                    "changes": {"l0000": "stale editor"},
                },
            ).status_code
            == 409
        )
        assert "user correction" in client.get(prefix + "/assets/lrc?version=original").text
        assert "new recognition" in client.get(prefix + f"/assets/lrc?version={version}").text
        assert len(client.get(prefix + "/versions").json()["versions"]) == 2
        comparison = client.get(prefix + f"/compare?left=original&right={version}").json()
        assert comparison["changes"]
        assert (
            client.post(
                prefix + "/versions/select",
                json={
                    "version": "original",
                    "expected_current": "original",
                },
            ).status_code
            == 409
        )
        assert (
            client.post(
                prefix + "/versions/select",
                json={
                    "version": "original",
                    "expected_current": version,
                },
            ).status_code
            == 200
        )
        assert client.get(prefix + "/lyrics").json()["changes"]["l0000"] == "user correction"
        assert client.get(prefix + "/result?version=../../bad").status_code == 404
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        assert len(client.get(prefix + "/versions").json()["versions"]) == 2
        assert client.get(prefix).json()["current_version"] == "original"


def test_failed_update_remains_playable_and_does_not_replace_result(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Missing optional model")

    monkeypatch.setattr("music_studio.ui.server.update_lyrics", fail)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        client.post(prefix + "/analyze", json={"scope": "lyrics"})
        record = wait_status(client, identifier, "failed")
        assert record["has_result"] and record["current_version"] == "original"
        assert client.get(prefix + "/result").status_code == 200
        assert client.get(prefix + "/assets/source").status_code == 200
        assert client.get(prefix + "/versions").json()["versions"][0]["status"] == "failed"


def test_full_reanalysis_creates_new_snapshot_and_legacy_export_stays_available(tmp_path):
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        original = sha256(tmp_path / identifier / "result/project.json")
        assert (
            client.post(
                prefix + "/analyze",
                json={
                    "scope": "full",
                    "quality": "text",
                    "base_version": "original",
                },
            ).status_code
            == 202
        )
        record = wait_status(client, identifier, "complete")
        assert record["current_version"] != "original"
        assert client.get(prefix + "/result").json()["settings"]["asr_model"] == "large-v3-turbo"
        assert sha256(tmp_path / identifier / "result/project.json") == original
        assert client.get(prefix + "/assets/midi?version=original").status_code == 200


def test_selective_retry_rejects_missing_sentence_and_snapshots_other_corrections(
    tmp_path, monkeypatch
):
    received = []

    def record_update(base, output, settings, **kwargs):
        received.append(kwargs)
        return fake_update(base, output, settings, **kwargs)

    monkeypatch.setattr("music_studio.ui.server.update_lyrics", record_update)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        options = {
            "scope": "retry",
            "base_version": "original",
            "edit_revision": 0,
            "line_id": "absent",
        }
        assert client.post(prefix + "/analyze", json=options).status_code == 422
        options["line_id"] = "l0000"
        assert client.post(prefix + "/analyze", json=options).status_code == 202
        wait_status(client, identifier, "complete")
        assert received[0]["retry_line"] == "l0000"
        assert received[0]["supplied"].segments[0].text == "wrong word"


def test_cancellation_keeps_old_result_and_blocks_version_switch_while_running(
    tmp_path, monkeypatch
):
    entered = threading.Event()

    def slow(base, output, settings, *, cancel_event, **kwargs):
        entered.set()
        assert cancel_event.wait(3)
        raise AnalysisCancelled("cancelled")

    monkeypatch.setattr("music_studio.ui.server.update_lyrics", slow)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        client.post(prefix + "/analyze", json={"scope": "lyrics"})
        assert entered.wait(1)
        assert client.get(prefix + "/result").status_code == 200
        assert (
            client.post(
                prefix + "/versions/select",
                json={
                    "version": "original",
                    "expected_current": "original",
                },
            ).status_code
            == 409
        )
        client.post(prefix + "/cancel", json={})
        record = wait_status(client, identifier, "cancelled")
        assert record["has_result"] and record["current_version"] == "original"


def test_alignment_snapshots_corrected_text_and_rejects_stale_editor(tmp_path, monkeypatch):
    monkeypatch.setattr("music_studio.ui.server.update_lyrics", fake_update)
    with TestClient(
        create_app(tmp_path, analyzer=finished_analysis), base_url="http://127.0.0.1"
    ) as client:
        identifier, prefix = initial(client)
        client.patch(
            prefix + "/lyrics",
            json={
                "revision": 0,
                "changes": {"l0000": "corrected words"},
            },
        )
        options = {
            "scope": "align",
            "base_version": "original",
            "edit_revision": 0,
            "language": "en",
        }
        assert client.post(prefix + "/analyze", json=options).status_code == 409
        options["edit_revision"] = 1
        assert client.post(prefix + "/analyze", json=options).status_code == 202
        wait_status(client, identifier, "complete")
        assert client.get(prefix + "/result").json()["lyrics"]["segments"][0]["text"] == (
            "corrected words"
        )


def test_lyrics_only_preserves_music_and_audio_with_new_word_links(tmp_path, monkeypatch):
    from test_ui import audio_bytes

    from music_studio.config import Settings

    source = tmp_path / "input.wav"
    source.write_bytes(audio_bytes())
    base, output = tmp_path / "base", tmp_path / "new"
    original = finished_analysis(source, base, Settings(melody_decoder="classic"))
    write_json(base / "analysis/melody.json", original.melody.model_dump())
    original.stages["melody"] = {
        "artifacts": {
            "analysis/melody.json": sha256(base / "analysis/melody.json"),
            "analysis/pitch.json": sha256(base / "analysis/pitch.json"),
        }
    }
    write_json(base / "project.json", original.model_dump())
    proposed = Lyrics.model_validate(
        {
            "language": "en",
            "timing_method": "test-new",
            "segments": [
                {
                    "id": "lnew",
                    "text": "better",
                    "start": 0.1,
                    "end": 0.4,
                    "words": [{"id": "wnew", "text": "better", "start": 0.1, "end": 0.4}],
                }
            ],
        }
    )

    def worker(request, log_path, **kwargs):
        assert request["stage"] == "lyrics"
        write_json(Path(request["result"]), proposed.model_dump())
        write_json(log_path.parent.parent / "analysis/lyrics.metrics.json", {"elapsed_seconds": 0})
        return proposed.model_dump()

    monkeypatch.setattr("music_studio.ui.revisions.run_worker", worker)
    result = update_lyrics(base, output, Settings(asr_model="large-v3-turbo"))
    for name in ("source", "vocals", "instrumental", "pitch"):
        assert sha256(base / original.assets[name]) == sha256(output / result.assets[name])
    assert result.settings["melody_decoder"] == "classic"
    assert result.melody.notes[0].lyric_word_ids == ["wnew"]
    assert result.melody.notes[0].pitch == original.melody.notes[0].pitch
    assert result.rhythm == original.rhythm and result.harmony == original.harmony
    from music_studio.validation import validate_project

    assert validate_project(output)["valid"]
    state = read_json(output / "run.json")
    assert state["source_sha256"] == original.audio.source_sha256
    assert state["stages"]["melody"]["inherited"]
    assert sha256(output / "analysis/melody.json") == sha256(base / "analysis/melody.json")
