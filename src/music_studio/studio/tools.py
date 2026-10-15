"""The same typed audio tools are exposed through MCP and Codex dynamic tools."""

from typing import Literal

from pydantic import Field

from .models import (
    AdoptRequest,
    ExportRequest,
    PreviewRequest,
    RevisionRequest,
    SelectionRequest,
    StrictModel,
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
