"""The same typed audio tools are exposed through MCP and Codex dynamic tools."""

from typing import Literal

from pydantic import Field

from .models import (
    AdoptRequest,
    ExportRequest,
    LocalTaskRequest,
    PreviewRequest,
    RevisionRequest,
    SelectionRequest,
    StrictModel,
    TranscriptPatch,
)
from .service import StudioError, StudioService


class ProjectArgs(StrictModel):
    project: str = Field(pattern=r"^[a-f0-9]{16}$")


class PreviewArgs(ProjectArgs, PreviewRequest):
    pass


class AdoptArgs(ProjectArgs, AdoptRequest):
    pass


class HistoryArgs(ProjectArgs, RevisionRequest):
    direction: Literal["undo", "redo"]


class ExportArgs(ProjectArgs, ExportRequest):
    pass


class SelectionArgs(ProjectArgs, SelectionRequest):
    pass


class EventArgs(ProjectArgs):
    after: int = Field(default=0, ge=0)


class ModelArgs(ProjectArgs):
    model: str = Field(min_length=1, max_length=80)


class TaskArgs(ProjectArgs, LocalTaskRequest):
    pass


class TaskIdArgs(ProjectArgs):
    task: str = Field(pattern=r"^[a-f0-9]{16}$")


class ArtifactArgs(ProjectArgs):
    asset: str = Field(
        pattern=r"^[a-f0-9]{16}$",
        description="Plain 16-character artifact id from task.artifacts; no asset: prefix. "
        "For reading, choose kind json or transcript, not audio or midi.",
    )


class TranscriptArgs(ArtifactArgs, TranscriptPatch):
    pass


class ToolCatalog:
    definitions = {
        "audio_list_projects": (StrictModel, "List imported audio projects. No filesystem access."),
        "audio_get_session": (
            ProjectArgs,
            "Inspect current audio, revision, selection, assets and previews. Use before editing.",
        ),
        "audio_set_selection": (
            SelectionArgs,
            "Set a sample-timeline selection shared with the UI. Does not alter audio or "
            "invalidate previews.",
        ),
        "audio_render_preview": (
            PreviewArgs,
            "Render typed audio operations as a new immutable preview. Does not adopt it. "
            "Times refer to each operation's input, in seconds. Mix uses matching full "
            "timelines. Return preview id to user.",
        ),
        "audio_adopt_preview": (
            AdoptArgs,
            "Keep a ready preview as current. Only when the user explicitly asks to keep/apply "
            "it. Requires its unchanged base revision. Reversible with undo.",
        ),
        "audio_history": (
            HistoryArgs,
            "Undo or redo the user's edit. Read current revision first.",
        ),
        "audio_export_wav": (
            ExportArgs,
            "Export a pinned asset/revision to WAV. Refuses clipping integer exports. Returns "
            "a local path. Do not upload this audio.",
        ),
        "audio_get_events": (
            EventArgs,
            "Read shared UI, MCP and Codex operation events after a sequence cursor.",
        ),
        "audio_list_models": (
            ProjectArgs,
            "List fixed local audio capabilities, licenses and separate runtime/weight status. "
            "Does not load models.",
        ),
        "audio_check_model": (
            ModelArgs,
            "Check a runtime by importing it in an isolated process. Offline; no installs or "
            "downloads. Cached weights are not a promise of accuracy or successful loading.",
        ),
        "audio_run_task": (
            TaskArgs,
            "Queue one local analysis on a pinned immutable input. Returns immediately. "
            "No automatic adoption. Use audio_get_tasks to observe completion and assets. "
            "For melody use separated vocals, isolated singing or humming when possible.",
        ),
        "audio_get_tasks": (
            ProjectArgs,
            "Read task status, failures, resource measurements and artifact IDs. "
            "Completion never changes the current edit.",
        ),
        "audio_cancel_task": (
            TaskIdArgs,
            "Cancel a queued or running local task; preserves originals and completed outputs.",
        ),
        "audio_read_artifact": (
            ArtifactArgs,
            "Read a task's JSON result, such as a transcript, notes or levels. "
            "Project scoped; never sends audio bytes. Large files remain download-only.",
        ),
        "audio_correct_transcript": (
            TranscriptArgs,
            "Save explicitly requested text corrections as a new immutable transcript version. "
            "Retains original text and estimated line timing; clears word times on changed lines. "
            "Requires the original artifact SHA256.",
        ),
    }

    def __init__(self, service: StudioService, actor="mcp", project: str | None = None):
        self.service, self.actor, self.project = service, actor, project

    def describe(self):
        return [
            {"name": name, "description": description, "inputSchema": model.model_json_schema()}
            for name, (model, description) in self.definitions.items()
        ]

    @staticmethod
    def compact_session(session):
        result = {k: v for k, v in session.items() if k != "waveform"}
        result["candidates"] = [
            {k: v for k, v in c.items() if k not in ("waveform", "file")}
            for c in result["candidates"]
        ]
        return result

    def call(self, name: str, arguments: dict):
        if name not in self.definitions:
            raise StudioError("Unknown audio tool")
        model = self.definitions[name][0].model_validate(arguments)
        if self.project is not None and hasattr(model, "project") and model.project != self.project:
            raise StudioError("This agent session belongs to another project", 403)
        if name == "audio_list_projects":
            projects = self.service.list_projects()
            return {
                "projects": [p for p in projects if self.project is None or p["id"] == self.project]
            }
        project = model.project
        if name == "audio_list_models":
            self.service.project_dir(project)
            return {"models": self.service.tasks.registry.list()}
        if name == "audio_check_model":
            self.service.project_dir(project)
            return self.service.tasks.registry.check(model.model)
        if name == "audio_run_task":
            request = LocalTaskRequest.model_validate(model.model_dump(exclude={"project"}))
            return self.service.tasks.submit(project, request, self.actor)
        if name == "audio_get_tasks":
            return {"tasks": self.service.tasks.list(project)}
        if name == "audio_cancel_task":
            return self.service.tasks.cancel(project, model.task, self.actor)
        if name == "audio_read_artifact":
            from ..io import read_json

            path, record = self.service.tasks.artifact_path(project, model.asset)
            if record["kind"] not in ("json", "transcript") or path.stat().st_size > 256 * 1024:
                raise StudioError(
                    "This result is audio, binary or too large; use the local download"
                )
            return {"asset": model.asset, "sha256": record["sha256"], "data": read_json(path)}
        if name == "audio_correct_transcript":
            from .transcripts import correct

            request = TranscriptPatch.model_validate(model.model_dump(exclude={"project", "asset"}))
            return correct(self.service, project, model.asset, request, self.actor)
        if name == "audio_get_session":
            return self.compact_session(self.service.session(project))
        if name == "audio_render_preview":
            request = PreviewRequest.model_validate(model.model_dump(exclude={"project"}))
            result = self.service.preview(project, request, self.actor)
            return {k: v for k, v in result.items() if k not in ("waveform", "file")}
        if name == "audio_set_selection":
            return self.service.selection(project, model, self.actor)
        if name == "audio_adopt_preview":
            return self.compact_session(
                self.service.adopt(project, model.candidate, model.revision, self.actor)
            )
        if name == "audio_history":
            return self.compact_session(
                self.service.history(project, model.revision, model.direction, self.actor)
            )
        if name == "audio_export_wav":
            return self.service.export(
                project, model.revision, model.asset, model.subtype, self.actor
            )
        return {"events": self.service.events(project, model.after)}
