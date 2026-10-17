"""Build an application update reusing a verified, published GPU runtime release."""

import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from installer_delivery import build_bootstrap, digest, write_checksums

from music_studio import __version__


def package(repo, wheel, desktop, base_manifest, tools, destination):
    destination.mkdir(parents=True, exist_ok=True)
    payload = destination / "build/application"
    if payload.exists():
        raise ValueError("Choose a fresh output directory for the application payload")
    site = payload / "runtime/Lib/site-packages"
    site.mkdir(parents=True)
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or ":" in name:
                raise ValueError("Unexpected wheel path")
        assert f"music_studio_local-{__version__}.dist-info/METADATA" in archive.namelist()
        archive.extractall(site)
    for path in desktop.iterdir():
        if path.is_file() and path.suffix in (".exe", ".config", ".dll"):
            shutil.copy2(path, payload / path.name)
    assert (payload / "Music Studio.exe").is_file()
    for source, name in (("src/music_studio/ui/static/icon.ico", "Music Studio.ico"),
                         ("QUICKSTART.md", "START-HERE.md"), ("LICENSE", "LICENSE"),
                         ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md")):
        shutil.copy2(repo / source, payload / name)
    subprocess.run([
        str(tools / "inno/ISCC.exe"), "/Qp", "/DApplicationUpdate=1",
        "/DRepo=" + str(repo), "/DPayload=" + str(payload),
        "/DDestination=" + str(destination), "/DBuildVersion=" + __version__,
        "/DChineseLanguage=" + str(tools / "ChineseSimplified.isl"),
        str(repo / "desktop/installer.iss"),
    ], check=True)
    update = destination / f"Music-Studio-{__version__}-Application-Update-x64.exe"
    delivery = json.loads(base_manifest.read_text(encoding="utf-8"))
    runtime_version = delivery["version"]
    delivery.update(version=__version__, runtime_version=runtime_version,
                    runtime_source=f"https://github.com/Hydr0g3ngz/music-studio/releases/"
                                   f"download/v{runtime_version}/")
    for old in ("application_wheel", "application_wheel_sha256"):
        delivery.pop(old, None)
    installer = destination / f"Music-Studio-{__version__}-Setup-x64.exe"
    build_bootstrap(repo, installer, __version__, delivery, wheel, application_update=update)
    files = [installer, update, destination / "DELIVERY.json"]
    write_checksums(destination, files)
    print(json.dumps({"assets": [{"name": p.name, "bytes": p.stat().st_size,
                                  "sha256": digest(p)} for p in files]}, indent=2))
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--desktop", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.wheel.resolve(), args.desktop.resolve(),
            args.base_manifest.resolve(), args.tools.resolve(), args.dist.resolve())
