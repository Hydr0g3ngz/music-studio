"""Immutable text corrections; retain line timing and never invent new word timing."""

import json
import time
import uuid

from ..export import timestamp
from ..io import read_json, sha256, write_json
from ..schema import Lyrics
from .service import StudioError


def write_text_exports(folder, lyrics):
    lines = [line for line in lyrics.segments if line.text.strip()]
    outputs = {
        "txt": "\n".join(line.text for line in lines) + "\n",
        "lrc": "\n".join(f"[{timestamp(line.start)}]{line.text}" for line in lines) + "\n",
        "srt": "\n\n".join(
            f"{i}\n{timestamp(line.start, srt=True)} --> "
            f"{timestamp(line.end, srt=True)}\n{line.text}"
            for i, line in enumerate(lines, 1)
        )
        + "\n",
    }
    for suffix, text in outputs.items():
        (folder / f"lyrics.{suffix}").write_text(text, encoding="utf-8")
    return [f"lyrics.{suffix}" for suffix in outputs]


def correct(service, project, asset, request, actor="ui"):
    with service.project_guard(project):
        source, parent = service.tasks.artifact_path(project, asset)
        if parent["kind"] != "transcript":
            raise StudioError("This asset is not an editable transcript")
        if sha256(source) != request.sha256 or parent["sha256"] != request.sha256:
            raise StudioError("Transcript changed; reopen it before editing", 409)
        lyrics = Lyrics.model_validate(read_json(source))
        known = {line.id for line in lyrics.segments}
        if not set(request.changes).issubset(known):
            raise StudioError("Unknown transcript line")
        changed = 0
        for line in lyrics.segments:
            if line.id in request.changes and line.text != request.changes[line.id]:
                line.text = request.changes[line.id]
                line.words = []
                line.review_reasons = [
                    "Text manually corrected; line timing retained, word timing cleared."
                ]
                changed += 1
        if not changed:
            raise StudioError("No text changes to save")
        lyrics.warnings.append(
            "Manual text correction. Changed lines retain estimated line times; "
            "word times are cleared."
        )
        version = int(parent.get("transcript_revision", 0)) + 1
        key = uuid.uuid4().hex[:16]
        folder = service.studio_dir(project, f"transcripts/{key}")
        write_json(folder / "lyrics.json", lyrics.model_dump())
        texts = write_text_exports(folder, lyrics)
        records = []
        names = [("lyrics.json", "transcript", "lyrics")]
        names.extend((name, "text", "lyrics-" + name.split(".")[-1]) for name in texts)
        for name, kind, role in names:
            file = folder / name
            record = {
                "id": key if kind == "transcript" else uuid.uuid4().hex[:16],
                "task": parent["task"],
                "model": parent["model"],
                "kind": kind,
                "role": role,
                "file": str(file.relative_to(service.project_dir(project))),
                "mime": "application/json" if kind == "transcript" else "text/plain; charset=utf-8",
                "sha256": sha256(file),
                "input_sha256": parent["input_sha256"],
                "parent": asset,
                "transcript_revision": version,
                "actor": actor,
                "created_at": time.time(),
            }
            records.append(record)
        with service.transaction() as db:
            for record in records:
                db.execute(
                    "INSERT INTO assets VALUES (?,?,?,?,?,?)",
                    (
                        record["id"],
                        project,
                        record["task"],
                        record["role"],
                        record["kind"],
                        json.dumps(record),
                    ),
                )
            service._event(
                db,
                project,
                actor,
                "transcript.corrected",
                {"asset": key, "parent": asset, "changed_lines": changed},
            )
        return {
            "asset": key,
            "artifacts": [{k: v for k, v in a.items() if k != "file"} for a in records],
        }
