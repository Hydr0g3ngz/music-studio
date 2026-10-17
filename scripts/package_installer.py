"""Build a self-contained Windows song-analysis installer, including basic models."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from music_studio import __version__

PYTHON_URL = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
PYTHON_SHA = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
DEMUCS_SHA = "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
CREPE_SHA = "133225604dedd2e4005f8bbd1bd0a2ec073ba8b7a6cd31ff6d5edbbfa3539986"
WHISPER_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
WHISPER_FILES = {
    "config.json": "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
    "model.bin": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
    "tokenizer.json": "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab",
    "vocabulary.txt": "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and digest(target) == expected:
        return
    temporary = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=90) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, 1024**2)
    if digest(temporary) != expected:
        raise ValueError("Downloaded checksum mismatch: " + target.name)
    temporary.replace(target)


def extract(archive, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        if any(not (folder / i.filename).resolve().is_relative_to(folder.resolve())
               for i in package.infolist()):
            raise ValueError("Invalid archive path")
        package.extractall(folder)


def stage(repo, wheel, target, tools, cache, engine_env=None, model_base=None):
    if target.exists():
        raise ValueError("Use a fresh payload directory")
    cache.mkdir(parents=True, exist_ok=True)
    runtime = target / "runtime"
    if engine_env:
        # Optional acceleration for maintainers: copy a verified CPU environment.
        # Its external app binding is discarded; the resulting payload is independent.
        shutil.copytree(engine_env, runtime,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log"))
    else:
        archive = cache / "python-3.12.10-embed-amd64.zip"
        download(PYTHON_URL, archive, PYTHON_SHA)
        extract(archive, runtime)
    (runtime / "python312._pth").write_text(
        "python312.zip\n.\nLib/site-packages\nimport site\n", encoding="utf-8",
    )
    python = runtime / "python.exe"
    environment = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH")}
    environment.update(PYTHONUTF8="1", PIP_CACHE_DIR=str(cache / "pip"))

    def run(*arguments):
        subprocess.run([str(python), "-X", "utf8", *map(str, arguments)],
                       check=True, env=environment)

    if not engine_env:
        with urllib.request.urlopen("https://pypi.org/pypi/pip/25.2/json") as response:
            metadata = json.load(response)
        spec = next(f for f in metadata["urls"] if f["filename"].endswith(".whl"))
        pip = cache / spec["filename"]
        download(spec["url"], pip, spec["digests"]["sha256"])
        run("-c", "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));"
            "runpy.run_module('pip',run_name='__main__')", pip, "install", pip)
        run("-m", "pip", "install", "setuptools==80.9.0", "wheel==0.45.1")
        run("-m", "pip", "install", "torch==2.5.1+cpu", "torchaudio==2.5.1+cpu",
            "--index-url", "https://download.pytorch.org/whl/cpu")
    run("-m", "pip", "install", "--no-build-isolation", "--no-warn-script-location",
        "-r", repo / "desktop/inference-requirements.txt", str(wheel.resolve()) + "[ui]")
    run("-m", "pip", "check")
    site = runtime / "Lib/site-packages"
    if any(site.glob("music_workbench_local*")) or (site / "music_studio/studio").exists():
        raise ValueError("Workbench content must not be included in Music Studio")
    crepe = site / "torchcrepe/assets/full.pth"
    if digest(crepe) != CREPE_SHA:
        raise ValueError("CREPE model checksum mismatch")
    models = target / "models"
    manifests = [{"file": str(crepe.relative_to(target)), "sha256": CREPE_SHA}]
    files = {
        "torch/hub/checkpoints/955717e8-8726e21a.th": (
            "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th",
            DEMUCS_SHA,
        ),
        **{f"whisper/models--Systran--faster-whisper-small/snapshots/{WHISPER_REVISION}/{name}": (
            f"https://huggingface.co/Systran/faster-whisper-small/resolve/"
            f"{WHISPER_REVISION}/{name}", checksum,
        ) for name, checksum in WHISPER_FILES.items()},
    }
    for relative, (url, expected) in files.items():
        destination = models / relative
        source = model_base / relative if model_base else None
        if source and source.is_file() and digest(source) == expected:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        else:
            download(url, destination, expected)
        manifests.append({"file": str(destination.relative_to(target)), "sha256": expected})
    (models / "BUNDLED-MODELS.json").write_text(json.dumps({
        "profile": "cpu-small", "models": ["Demucs htdemucs", "CREPE full", "Whisper small"],
        "files": manifests,
    }, indent=2), encoding="utf-8")
    subprocess.run([
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
        str(repo / "scripts/build-desktop.ps1"), "-Output", str(target / "Music Studio.exe"),
        "-Sdk", str(tools / "webview2"),
    ], check=True)
    for source, name in ((repo / "LICENSE", "LICENSE"),
                         (repo / "THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
                         (repo / "QUICKSTART.md", "START-HERE.md")):
        shutil.copyfile(source, target / name)
    shutil.copytree(repo / "desktop/model-licenses", target / "model-licenses")
    for name, metadata in (("Demucs", "demucs-4.0.1"), ("CREPE", "torchcrepe-0.0.24")):
        shutil.copyfile(site / (metadata + ".dist-info/licenses/LICENSE"),
                        target / "model-licenses" / (name + "-LICENSE.txt"))
    dependencies = []
    for path in sorted(site.glob("*.dist-info/METADATA")):
        value = dict(line.split(": ", 1) for line in path.read_text(encoding="utf-8").splitlines()
                     if line.startswith(("Name: ", "Version: ")))
        dependencies.append(value)
    (target / "DEPENDENCIES.json").write_text(json.dumps({
        "version": __version__, "python_sha256": PYTHON_SHA, "dependencies": dependencies,
    }, indent=2), encoding="utf-8")


def compile_installer(repo, payload, output, tools):
    output.mkdir(parents=True, exist_ok=True)
    prerequisite = tools / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    environment = {k: v for k, v in os.environ.items() if k != "PSModulePath"}
    subprocess.run([
        shutil.which("pwsh") or "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(repo / "scripts/verify-desktop-prerequisite.ps1"), "-Path", str(prerequisite),
    ], check=True, env=environment)
    subprocess.run([
        str(tools / "inno/ISCC.exe"), "/Qp", "/DRepo=" + str(repo),
        "/DPayload=" + str(payload), "/DDestination=" + str(output),
        "/DBuildVersion=" + __version__,
        "/DChineseLanguage=" + str(tools / "ChineseSimplified.isl"),
        "/DWebViewInstaller=" + str(prerequisite), str(repo / "desktop/installer.iss"),
    ], check=True)
    installer = output / f"Music-Studio-{__version__}-Setup-x64.exe"
    checksum = digest(installer)
    (output / "SHA256SUMS.txt").write_text(checksum + "  " + installer.name + "\n")
    print(json.dumps({"installer": str(installer), "bytes": installer.stat().st_size,
                      "sha256": checksum}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--engine-env", type=Path)
    parser.add_argument("--model-base", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".artifacts/installer-downloads"))
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not args.compile_only:
        if not args.wheel:
            parser.error("--wheel is required when staging")
        stage(root, args.wheel, args.payload.resolve(), args.tools.resolve(), args.cache.resolve(),
              args.engine_env, args.model_base)
    compile_installer(root, args.payload.resolve(), args.dist.resolve(), args.tools.resolve())
