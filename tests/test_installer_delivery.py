"""Release updates must carry the native window as well as the Python UI."""

import importlib.util
import json
import subprocess
from pathlib import Path


def test_reused_runtime_bootstrap_embeds_native_update_and_keeps_base_source(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "delivery", repo / "scripts/installer_delivery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wheel = tmp_path / "app.whl"
    wheel.write_bytes(b"wheel")
    update = tmp_path / "native-update.exe"
    update.write_bytes(b"native and Python application installer")
    installer = tmp_path / "Setup.exe"
    calls = []

    def compile_stub(command, **kwargs):
        calls.append(command)
        installer.write_bytes(b"compiled bootstrap")

    monkeypatch.setenv("SystemRoot", str(tmp_path))
    monkeypatch.setattr(subprocess, "run", compile_stub)
    delivery = {"runtime_version": "0.1.4", "offline_sha256": "0" * 64,
                "offline_bytes": 20, "parts": [
                    {"name": "runtime-0.1.4.bin", "size": 20, "sha256": "1" * 64}]}
    module.build_bootstrap(repo, installer, "0.1.5", delivery, wheel,
                           application_update=update)
    command = calls[0]
    assert any(arg.endswith(",MusicStudio.ApplicationUpdate.exe") for arg in command)
    assert any(arg.endswith(",MusicStudio.Update.whl") for arg in command)
    source = (tmp_path / "build/Installer.generated.cs").read_text(encoding="utf-8")
    assert 'const string Version="0.1.5";' in source
    assert 'const string BaseVersion="0.1.4";' in source
    assert "@@" not in source
    metadata = json.loads((tmp_path / "DELIVERY.json").read_text())
    assert metadata["application_update_sha256"] == module.digest(update)
    assert metadata["application_wheel_sha256"] == module.digest(wheel)
