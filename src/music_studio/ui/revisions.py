"""Immutable analysis revisions with version-bound user corrections."""

import copy
import os
import re
import shutil
import time
from pathlib import Path

from fastapi import HTTPException

from ..config import Settings
from ..export import export_project, link_words
from ..io import read_json, sha256, write_json
from ..pipeline import AnalysisCancelled, run_worker
from ..schema import Lyrics, Project


def result_folder(directory: Path, version: str) -> Path:
    if version == "original":
        return directory / "result"
    if not re.fullmatch(r"[a-f0-9]{16}", version):
        raise HTTPException(404, "分析版本不存在")
    candidate = directory / "revisions" / version
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(directory.resolve()):
        raise HTTPException(404, "分析版本不存在")
    return candidate


def edits_path(folder: Path) -> Path:
    return folder.parent / "lyrics-edits.json" if folder.name == "result" else folder / "edits.json"


def edits_state(folder: Path) -> dict:
    path = edits_path(folder)
    return read_json(path) if path.exists() else {"revision": 0, "changes": {}}


def edited_project(folder: Path, project: Project) -> Project:
    edits = edits_state(folder)
    result = project.model_copy(deep=True)
    removed = set()
    for line in result.lyrics.segments:
        if line.id in edits["changes"]:
            removed.update(w.id for w in line.words)
            line.text = edits["changes"][line.id]
            line.words = []
    for note in result.melody.notes:
        note.lyric_word_ids = [w for w in note.lyric_word_ids if w not in removed]
    if edits["changes"]:
        result.lyrics.warnings.append(
            "User-corrected lines retain sentence times; word times and note-word links "
            "on these lines are omitted until realignment. Raw recognition is preserved."
        )
    return result


def versions(directory: Path, record: dict) -> list[dict]:
    result = []
    original = directory / "result/project.json"
    if original.is_file():
        project = read_json(original)
        result.append(
            {
                "id": "original",
                "status": "complete",
                "scope": "full",
                "created_at": record["created_at"],
                "settings": project["settings"],
                "timing_method": project["lyrics"]["timing_method"],
                "lyrics_count": len(project["lyrics"]["segments"]),
                "edits_count": len(edits_state(original.parent)["changes"]),
            }
        )
    for path in sorted((directory / "revisions").glob("*.json")):
        if not re.fullmatch(r"[a-f0-9]{16}", path.stem):
            continue
        item = read_json(path)
        folder = result_folder(directory, path.stem)
        item["edits_count"] = len(edits_state(folder)["changes"])
        result.append(item)
    return sorted(result, key=lambda item: item["created_at"], reverse=True)


def link_file(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def inherit_artifacts(base: Path, output: Path, project: Project):
    """Keep inherited stage manifests verifiable in the new result directory."""
    files = {project.assets[name]: None for name in ("source", "vocals", "instrumental", "pitch")}
    for name, stage in project.stages.items():
        if name != "lyrics":
            files.update(stage.get("artifacts", {}))
    for relative, digest in files.items():
        source, target = (base / relative).resolve(), (output / relative).resolve()
        if not source.is_relative_to(base.resolve()) or not target.is_relative_to(output.resolve()):
            raise ValueError("Inherited artifact is outside the result directory")
        actual = sha256(source)
        if digest is not None and actual != digest:
            raise ValueError(f"Inherited artifact changed: {relative}")
        if target.exists():
            if sha256(target) != actual:
                raise ValueError(f"Revision artifact differs: {relative}")
        else:
            link_file(source, target)


def update_lyrics(
    base: Path,
    output: Path,
    settings: Settings,
    *,
    supplied: Lyrics | None = None,
    reference: bool = False,
    retry_line: str | None = None,
    progress=print,
    cancel_event=None,
) -> Project:
    """Rerun recognition/alignment only. Musical predictions and audio remain unchanged."""
    previous = Project.model_validate(read_json(base / "project.json"))
    inherit_artifacts(base, output, previous)
    if (base / "analysis/anchor-guide.json").is_file():
        link_file(base / "analysis/anchor-guide.json", output / "analysis/anchor-guide.json")
    config = settings.resolved().model_dump()
    # Preserve music configuration/provenance instead of relabelling inherited music as new.
    merged = copy.deepcopy(previous.settings)
    merged.pop("precomputed_demo", None)
    fields = [
        "lyrics_alignment",
        "anchor_model",
        "lyrics_input",
        "lyrics_python",
        "language",
        "device",
        "offline",
        "model_dir",
        "threads",
    ]
    if supplied is None or retry_line:
        fields.extend(["asr_backend", "asr_model", "asr_revision", "asr_segmentation", "seed"])
    for name in fields:
        merged[name] = config[name]
    if supplied is None:
        merged["lyrics_text_source"] = "automatic"
    state = {
        "status": "running",
        "active_stage": "lyrics",
        "stages": {},
        "source_sha256": previous.audio.source_sha256,
        "executed_stages": ["lyrics"],
    }
    write_json(output / "run.json", state)
    target = output / "analysis/lyrics.json"
    if supplied is not None:
        write_json(output / "analysis/lyrics-input.json", supplied.model_dump())
    started = time.perf_counter()
    progress(
        "正在重新识别这一句…"
        if retry_line
        else "正在对齐提供的歌词…"
        if supplied is not None
        else "正在重新识别歌词…"
    )
    result = run_worker(
        {
            "stage": "retry" if retry_line else "align" if supplied is not None else "lyrics",
            "settings": config,
            "output": str(output.resolve()),
            "result": str(target.resolve()),
            "reference": reference,
            "preserve_lines": supplied is not None,
            "line_id": retry_line,
        },
        output / "logs/lyrics.log",
        cancel_event=cancel_event,
    )
    if cancel_event is not None and cancel_event.is_set():
        raise AnalysisCancelled("Analysis cancelled")
    project = previous.model_copy(deep=True)
    project.lyrics = Lyrics.model_validate(result)
    for line in project.lyrics.segments:
        line.end = min(line.end, project.audio.duration)
        for word in line.words:
            word.end = min(word.end, project.audio.duration)
    for note in project.melody.notes:
        note.lyric_word_ids = []
    link_words(project.melody, project.lyrics)
    project.settings = merged
    project.stages = {
        name: {**value, "inherited": True}
        for name, value in previous.stages.items()
        if name != "lyrics"
    }
    project.stages["lyrics"] = {
        "inherited": False,
        "scope": "selective_retry"
        if retry_line
        else "alignment"
        if supplied is not None
        else "recognition",
        "artifacts": {"analysis/lyrics.json": sha256(target)},
        "metrics": read_json(target.with_suffix(".metrics.json")),
        "wall_seconds": round(time.perf_counter() - started, 3),
        "engine_hashes": {
            str(path.relative_to(Path(__file__).parents[1])): sha256(path)
            for path in Path(__file__).parents[1].rglob("*.py")
            if "ui" not in path.relative_to(Path(__file__).parents[1]).parts
        },
    }
    if supplied is not None:
        project.settings["lyrics_text_source"] = (
            "selective_retry" if retry_line else "user_reference" if reference else "user_corrected"
        )
        project.settings["lyrics_input_sha256"] = sha256(output / "analysis/lyrics-input.json")
    project = Project.model_validate(project.model_dump())
    export_project(project, output)
    write_json(output / "project.json", project.model_dump())
    state.update(status="complete", active_stage=None, stages=project.stages)
    write_json(output / "run.json", state)
    return project
