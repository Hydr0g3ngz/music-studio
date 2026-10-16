import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def setup_module_source():
    path = Path(__file__).resolve().parents[1] / "scripts/setup_ace.py"
    spec = importlib.util.spec_from_file_location("creation_setup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_implementation_is_pinned_without_mutating_downloaded_code(tmp_path):
    setup = setup_module_source()
    snapshot, source = tmp_path / "weights", tmp_path / "source"
    downloaded = {
        "acestep-v15-turbo/model.safetensors": b"fixture weights",
        "acestep-v15-turbo/modeling.py": b"older checkpoint implementation",
        "vae/config.json": b"{}",
    }
    for name, raw in downloaded.items():
        target = snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    (snapshot / "music-studio-manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {"file": name, "sha256": hashlib.sha256(raw).hexdigest()}
                    for name, raw in downloaded.items()
                ]
            }
        ),
        encoding="utf-8",
    )
    code = source / "acestep/models/turbo/modeling.py"
    code.parent.mkdir(parents=True)
    code.write_text("pinned authoritative implementation", encoding="utf-8")
    view = setup.prepare_model_view(source, snapshot)
    assert (view / "acestep-v15-turbo/modeling.py").read_bytes() == code.read_bytes()
    assert (snapshot / "acestep-v15-turbo/modeling.py").read_bytes() == downloaded[
        "acestep-v15-turbo/modeling.py"
    ]
    manifest = json.loads((view / "music-studio-manifest.json").read_text())
    assert manifest["source_revision"] == setup.SOURCE
    assert manifest["model_revision"] == setup.MODEL
    for item in manifest["files"]:
        assert setup.digest(view / item["file"]) == item["sha256"]
    assert setup.prepare_model_view(source, snapshot) == view
    (view / "acestep-v15-turbo/modeling.py").write_text("unexpected change", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Resolved checkpoint changed"):
        setup.prepare_model_view(source, snapshot)
