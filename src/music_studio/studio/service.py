"""One local state/operation service for HTTP, MCP and embedded agent clients."""

import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from ..audio import decode_audio
from ..io import fingerprint, read_json, sha256, write_json
from . import dsp
from .models import PreviewRequest


class StudioError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class StudioService:
    def __init__(self, workspace: Path, settings=None):
        self.root = workspace.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / ".studio.sqlite3"
        self.settings = settings
        self._task_manager = None
        self._task_lock = threading.Lock()
        if self.database.is_symlink() or self.database.resolve().parent != self.root:
            raise StudioError("Invalid workspace state database")
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    project TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, base_revision INTEGER NOT NULL,
                    status TEXT NOT NULL, data TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
                    actor TEXT NOT NULL, kind TEXT NOT NULL,
                    data TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_project ON events(project, seq);
                CREATE INDEX IF NOT EXISTS candidates_project ON candidates(project, created);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, status TEXT NOT NULL,
                    data TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS tasks_project ON tasks(project, created);
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, task TEXT NOT NULL,
                    role TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assets_project ON assets(project);
            """)

    @property
    def tasks(self):
        with self._task_lock:
            if self._task_manager is None:
                from .tasks import TaskManager

                self._task_manager = TaskManager(self, self.settings)
            return self._task_manager

    def close(self):
        if self._task_manager is not None:
            self._task_manager.close()

    @contextmanager
    def project_guard(self, project):
        self.project_dir(project)
        guards = self.root / ".studio-guards"
        if guards.is_symlink():
            raise StudioError("Invalid project lock directory")
        guards.mkdir(exist_ok=True)
        with FileLock(str(guards / f"{project}.lock"), timeout=30):
            yield

    def registered_assets(self, project):
        self.project_dir(project)
        with self.connection() as db:
            return [
                json.loads(row["data"])
                for row in db.execute(
                    "SELECT data FROM assets WHERE project=? ORDER BY rowid DESC", (project,)
                )
            ]

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def project_dir(self, project: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{16}", project):
            raise StudioError("Project does not exist", 404)
        path = self.root / project
        if (
            path.is_symlink()
            or path.resolve().parent != self.root
            or not (path / "job.json").is_file()
        ):
            raise StudioError("Project does not exist", 404)
        return path

    @staticmethod
    def safe_file(folder: Path, relative: str) -> Path:
        path = (folder / relative).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            raise StudioError("Audio asset is unavailable", 404)
        return path

    def studio_dir(self, project: str, relative: str = "") -> Path:
        folder = self.project_dir(project)
        path = folder / ".studio" / relative
        if not path.resolve().is_relative_to(folder.resolve()):
            raise StudioError("Invalid project working directory")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_projects(self) -> list[dict]:
        result = []
        for path in self.root.glob("*/job.json"):
            try:
                self.project_dir(path.parent.name)
                record = read_json(path)
                result.append(
                    {
                        "id": record["id"],
                        "title": record["title"],
                        "status": record["status"],
                        "created_at": record["created_at"],
                    }
                )
            except (OSError, ValueError, KeyError):
                continue
        return sorted(result, key=lambda item: item["created_at"], reverse=True)

    def _source(self, project: str) -> Path:
        folder = self.project_dir(project)
        studio = self.studio_dir(project)
        with FileLock(str(studio / "prepare.lock"), timeout=30):
            metadata = studio / "source.json"
            if metadata.is_file():
                return self.safe_file(folder, read_json(metadata)["file"])
            record = read_json(folder / "job.json")
            version = record.get("current_version", "original")
            if version != "original" and not re.fullmatch(r"[a-f0-9]{16}", version):
                raise StudioError("Invalid analysis version")
            result = folder / "result" if version == "original" else folder / "revisions" / version
            # Existing analysis already owns a canonical, immutable source WAV.
            if version == "original" or re.fullmatch(r"[a-f0-9]{16}", version):
                if (result / "project.json").is_file():
                    existing = read_json(result / "project.json")
                    source = self.safe_file(
                        folder, str((result / existing["assets"]["source"]).relative_to(folder))
                    )
                    write_json(metadata, {"file": str(source.relative_to(folder)), "reused": True})
                    return source
            original = self.safe_file(folder, str(Path("input") / record["filename"]))
            source = studio / "source.wav"
            try:
                decode_audio(original, source, sha256(original))
            except ImportError as error:
                raise StudioError(
                    "Install the [audio] dependencies to decode this file", 503
                ) from error
            write_json(metadata, {"file": str(source.relative_to(folder)), "reused": False})
            return source

    def assets(self, project: str) -> dict[str, Path]:
        folder = self.project_dir(project)
        result = {"source": self._source(project)}
        job = read_json(folder / "job.json")
        version = job.get("current_version", "original")
        selected = folder / "result"
        if version != "original":
            if not re.fullmatch(r"[a-f0-9]{16}", version):
                raise StudioError("Invalid analysis version")
            selected = folder / "revisions" / version
        if (selected / "project.json").is_file():
            project_data = read_json(selected / "project.json")
            for kind in ("vocals", "instrumental"):
                if kind in project_data["assets"]:
                    result[kind] = self.safe_file(
                        folder, str((selected / project_data["assets"][kind]).relative_to(folder))
                    )
                    self._register_analysis_asset(
                        project, version, kind, result[kind], result["source"]
                    )
        return result

    def _register_analysis_asset(self, project, version, role, path, source):
        relative = path.relative_to(self.project_dir(project)).as_posix()
        key = fingerprint({"project": project, "file": relative, "role": role})[:16]
        with self.connection() as db:
            if db.execute("SELECT 1 FROM assets WHERE id=?", (key,)).fetchone():
                return key
        record = {
            "id": key,
            "task": f"classic:{version}",
            "role": role,
            "kind": "audio",
            "model": "classic-analysis",
            "analysis_version": version,
            "file": relative,
            "mime": "audio/ogg" if path.suffix == ".ogg" else "audio/wav",
            "sha256": sha256(path),
            "input_sha256": sha256(source),
            "audio": dsp.inspect_audio(path),
        }
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?)",
                (
                    key,
                    project,
                    record["task"],
                    role,
                    "audio",
                    json.dumps(record),
                ),
            )
        return key

    def _row(self, db, project: str):
        row = db.execute("SELECT * FROM sessions WHERE project=?", (project,)).fetchone()
        if row is None:
            state = {"active": "source", "past": [], "future": []}
            db.execute("INSERT INTO sessions VALUES (?, 0, ?)", (project, json.dumps(state)))
            row = db.execute("SELECT * FROM sessions WHERE project=?", (project,)).fetchone()
        return row, json.loads(row["state"])

    @staticmethod
    def _check_revision(row, revision):
        if row["revision"] != revision:
            raise StudioError("The project changed; refresh before applying this operation", 409)

    @staticmethod
    def _event(db, project, actor, kind, data):
        if actor not in ("ui", "mcp", "codex", "system"):
            raise ValueError("Invalid operation actor")
        db.execute(
            "INSERT INTO events(project,actor,kind,data,created) VALUES (?,?,?,?,?)",
            (project, actor, kind, json.dumps(data, ensure_ascii=False), time.time()),
        )

    def _candidate(self, db, project, candidate):
        row = db.execute(
            "SELECT * FROM candidates WHERE project=? AND id=?", (project, candidate)
        ).fetchone()
        if row is None:
            raise StudioError("Preview does not exist", 404)
        return {**json.loads(row["data"]), "status": row["status"]}

    def _resolve(self, project: str, asset: str, available: dict[str, Path]) -> Path:
        if asset in available:
            return available[asset]
        if re.fullmatch(r"candidate:[a-f0-9]{16}", asset):
            with self.connection() as db:
                candidate = self._candidate(db, project, asset.split(":")[1])
            if candidate["status"] != "ready":
                raise StudioError("Preview is not ready", 409)
            return self.safe_file(self.project_dir(project), candidate["file"])
        if re.fullmatch(r"asset:[a-f0-9]{16}", asset):
            with self.connection() as db:
                row = db.execute(
                    "SELECT data FROM assets WHERE project=? AND id=? AND kind='audio'",
                    (project, asset.split(":")[1]),
                ).fetchone()
            if row is not None:
                return self.safe_file(self.project_dir(project), json.loads(row["data"])["file"])
        raise StudioError("Audio asset is unavailable", 404)

    def session(self, project: str) -> dict:
        available = self.assets(project)
        registered = self.registered_assets(project)
        analysis_assets = {
            role: "asset:"
            + fingerprint(
                {
                    "project": project,
                    "file": available[role].relative_to(self.project_dir(project)).as_posix(),
                    "role": role,
                }
            )[:16]
            for role in ("vocals", "instrumental")
            if role in available
        }
        groups = {}
        for asset in registered:
            if asset["kind"] == "audio" and asset["role"] in ("vocals", "instrumental"):
                groups.setdefault(asset["task"], {})[asset["role"]] = asset
        mix_pairs = []
        for task, group in groups.items():
            if set(group) != {"vocals", "instrumental"}:
                continue
            vocal, backing = group["vocals"], group["instrumental"]
            if vocal["input_sha256"] != backing["input_sha256"] or any(
                vocal["audio"][key] != backing["audio"][key]
                for key in ("frames", "sample_rate", "channels")
            ):
                continue
            mix_pairs.append(
                {
                    "task": task,
                    "vocals": "asset:" + vocal["id"],
                    "instrumental": "asset:" + backing["id"],
                    "audio": vocal["audio"],
                }
            )
        mix_pairs.sort(key=lambda pair: pair["task"].startswith("classic:"))
        with self.transaction() as db:
            row, state = self._row(db, project)
            revision = row["revision"]
            candidates = [
                {**json.loads(r["data"]), "status": r["status"]}
                for r in db.execute(
                    "SELECT * FROM candidates WHERE project=? ORDER BY created DESC LIMIT 30",
                    (project,),
                )
            ]
        active = self._resolve(project, state["active"], available)
        return {
            "project": project,
            "revision": revision,
            "active": state["active"],
            "can_undo": bool(state["past"]),
            "can_redo": bool(state["future"]),
            "audio": dsp.inspect_audio(active),
            "waveform": dsp.peaks(active),
            "assets": list(available),
            "analysis_assets": analysis_assets,
            "mix_pairs": mix_pairs,
            "candidates": candidates,
            "selection": state.get("selection"),
            "registered_assets": [
                {k: v for k, v in asset.items() if k != "file"} for asset in registered
            ],
        }

    def selection(self, project, request, actor="ui"):
        available = self.assets(project)
        with self.transaction() as db:
            row, state = self._row(db, project)
            self._check_revision(row, request.revision)
            asset = state["active"] if request.asset == "current" else request.asset
            path = self._resolve(project, asset, available)
            import soundfile as sf

            info = sf.info(path)
            if request.end <= request.start or request.end > info.frames / info.samplerate + 1e-9:
                raise StudioError("Selection must fit within the audio")
            selected = {"asset": asset, "start": request.start, "end": request.end}
            if state.get("selection") == selected:
                return selected
            state["selection"] = selected
            db.execute("UPDATE sessions SET state=? WHERE project=?", (json.dumps(state), project))
            self._event(db, project, actor, "selection.changed", selected)
        return selected

    def asset_path(self, project: str, asset: str = "current") -> Path:
        available = self.assets(project)
        if asset == "current":
            with self.transaction() as db:
                _, state = self._row(db, project)
            asset = state["active"]
        return self._resolve(project, asset, available)

    def preview(self, project: str, request: PreviewRequest, actor: str = "ui") -> dict:
        available = self.assets(project)
        with self.transaction() as db:
            row, state = self._row(db, project)
            self._check_revision(row, request.revision)
            asset = state["active"] if request.asset == "current" else request.asset
        source = self._resolve(project, asset, available)
        available["current"] = source
        hashes = {"input": sha256(source)}
        for operation in request.operations:
            if operation.type == "mix":
                for track in operation.tracks:
                    available[track.asset] = self._resolve(project, track.asset, available)
                    hashes[track.asset] = sha256(available[track.asset])
        candidate = uuid.uuid4().hex[:16]
        folder = self.project_dir(project)
        output = self.studio_dir(project, f"candidates/{candidate}")
        data = {
            "id": candidate,
            "base_revision": request.revision,
            "source_asset": asset,
            "operations": [op.model_dump() for op in request.operations],
            "input_sha256": hashes,
            "actor": actor,
            "created_at": time.time(),
        }
        with self.transaction() as db:
            row, _ = self._row(db, project)
            self._check_revision(row, request.revision)
            db.execute(
                "INSERT INTO candidates VALUES (?,?,?,?,?,?)",
                (candidate, project, request.revision, "rendering", json.dumps(data), time.time()),
            )
            self._event(db, project, actor, "preview.started", {"candidate": candidate})
        try:
            current = source
            processing = []
            for index, operation in enumerate(request.operations):
                destination = output / f"step-{index:02d}.wav"
                processing.append(dsp.process(current, destination, operation, available))
                current = destination
            if sha256(source) != hashes["input"]:
                raise StudioError("Source changed during rendering; import it again", 409)
            if any(
                sha256(available[key]) != value for key, value in hashes.items() if key != "input"
            ):
                raise StudioError(
                    "A mix input changed during rendering; generate a new preview", 409
                )
            data.update(
                file=str(current.relative_to(folder)),
                sha256=sha256(current),
                audio=dsp.inspect_audio(current),
                waveform=dsp.peaks(current),
                processing=processing,
            )
        except Exception as error:
            data["error"] = str(error)
            with self.transaction() as db:
                db.execute(
                    "UPDATE candidates SET status='failed',data=? WHERE id=?",
                    (json.dumps(data), candidate),
                )
                self._event(
                    db,
                    project,
                    actor,
                    "preview.failed",
                    {"candidate": candidate, "error": str(error)},
                )
            raise
        with self.transaction() as db:
            db.execute(
                "UPDATE candidates SET status='ready',data=? WHERE id=?",
                (json.dumps(data), candidate),
            )
            self._event(db, project, actor, "preview.ready", {"candidate": candidate})
            row, _ = self._row(db, project)
            can_adopt = row["revision"] == request.revision
        return {**data, "status": "ready", "can_adopt": can_adopt}

    def comparison(self, project, reference, processed, actor="ui", notify=False):
        from urllib.parse import quote

        from .loudness import measure

        with self.transaction() as db:
            _, state = self._row(db, project)
            refs = [state["active"] if a == "current" else a for a in (reference, processed)]
        paths = [self.asset_path(project, ref) for ref in refs]
        hashes = [sha256(path) for path in paths]
        levels = [measure(path) for path in paths]
        if any(levels[0][key] != levels[1][key] for key in ("frames", "sample_rate", "channels")):
            raise StudioError("A/B comparison needs the same length, sample rate and channels")
        if any(sha256(path) != digest for path, digest in zip(paths, hashes, strict=True)):
            raise StudioError("Comparison audio changed; prepare a new comparison", 409)
        measurable = all(level["integrated_lufs"] is not None for level in levels)
        target = min(level["integrated_lufs"] for level in levels) if measurable else None
        gains = (
            [10 ** ((target - level["integrated_lufs"]) / 20) for level in levels]
            if measurable
            else [1, 1]
        )
        result = {
            "reference": refs[0],
            "processed": refs[1],
            "a": {
                "url": f"/api/projects/{project}/studio/assets/{quote(refs[0], safe='')}",
                "sha256": hashes[0],
                "levels": levels[0],
                "matched_gain": gains[0],
            },
            "b": {
                "url": f"/api/projects/{project}/studio/assets/{quote(refs[1], safe='')}",
                "sha256": hashes[1],
                "levels": levels[1],
                "matched_gain": gains[1],
            },
            "duration": levels[0]["duration"],
            "matching_available": measurable,
            "matching": "Attenuate to the quieter whole-file integrated LUFS; never boost",
        }
        if notify:
            with self.transaction() as db:
                self._event(
                    db,
                    project,
                    actor,
                    "comparison.prepared",
                    {"reference": refs[0], "processed": refs[1]},
                )
        return result

    def adopt(self, project: str, candidate: str, revision: int, actor: str = "ui") -> dict:
        self.project_dir(project)
        with self.transaction() as db:
            row, state = self._row(db, project)
            self._check_revision(row, revision)
            preview = self._candidate(db, project, candidate)
            if preview["status"] != "ready" or preview["base_revision"] != revision:
                raise StudioError(
                    "This preview is stale or incomplete; generate a new preview", 409
                )
            self.safe_file(self.project_dir(project), preview["file"])
            if (
                sha256(self.safe_file(self.project_dir(project), preview["file"]))
                != preview["sha256"]
            ):
                raise StudioError("Preview audio changed; generate a new preview", 409)
            state["past"] = (state["past"] + [state["active"]])[-50:]
            state.update(active=f"candidate:{candidate}", future=[])
            db.execute(
                "UPDATE sessions SET revision=revision+1,state=? WHERE project=?",
                (json.dumps(state), project),
            )
            self._event(
                db,
                project,
                actor,
                "preview.adopted",
                {"candidate": candidate, "revision": revision + 1},
            )
        return self.session(project)

    def history(self, project: str, revision: int, direction: str, actor: str = "ui") -> dict:
        self.project_dir(project)
        if direction not in ("undo", "redo"):
            raise StudioError("Invalid history action")
        origin, target = ("past", "future") if direction == "undo" else ("future", "past")
        with self.transaction() as db:
            row, state = self._row(db, project)
            self._check_revision(row, revision)
            if not state[origin]:
                raise StudioError("No operation to undo or redo", 409)
            state[target].append(state["active"])
            state["active"] = state[origin].pop()
            db.execute(
                "UPDATE sessions SET revision=revision+1,state=? WHERE project=?",
                (json.dumps(state), project),
            )
            self._event(db, project, actor, f"history.{direction}", {"revision": revision + 1})
        return self.session(project)

    def events(self, project: str, after: int = 0) -> list[dict]:
        self.project_dir(project)
        with self.connection() as db:
            return [
                {**dict(row), "data": json.loads(row["data"])}
                for row in db.execute(
                    "SELECT * FROM events WHERE project=? AND seq>? ORDER BY seq LIMIT 100",
                    (project, after),
                )
            ]

    def export(
        self,
        project: str,
        revision: int,
        asset: str = "current",
        subtype: str = "PCM_24",
        actor: str = "ui",
    ) -> dict:
        available = self.assets(project)
        with self.transaction() as db:
            row, state = self._row(db, project)
            self._check_revision(row, revision)
            asset = state["active"] if asset == "current" else asset
        source = self._resolve(project, asset, available)
        folder = self.studio_dir(project, "exports")
        key = fingerprint({"sha256": sha256(source), "subtype": subtype})[:16]
        if subtype not in ("PCM_16", "PCM_24", "FLOAT"):
            raise StudioError("Unsupported export format")
        destination = folder / f"{key}.wav"
        with FileLock(str(destination.with_suffix(".lock")), timeout=30):
            info = dsp.export_audio(source, destination, subtype)
        result = {
            "id": key,
            "path": str(destination),
            "audio": info,
            "sha256": sha256(destination),
            "asset": asset,
            "revision": revision,
        }
        with self.transaction() as db:
            self._event(
                db,
                project,
                actor,
                "audio.exported",
                {
                    "id": key,
                    "asset": asset,
                    "revision": revision,
                    "subtype": subtype,
                },
            )
        return result
