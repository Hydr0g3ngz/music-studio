"""Keep GitHub assets below 2 GiB; a native installer fetches verified data parts."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ASSET_LIMIT = 2 * 1024**3
PART_SIZE = 1_500_000_000


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_bootstrap(repo, installer, version, delivery, wheel, application_update=None):
    folder = installer.parent
    template = (repo / "desktop/Installer.cs.in").read_text(encoding="utf-8")
    rows = [f'new Part("{p["name"]}",{p["size"]}L,"{p["sha256"]}")'
            for p in delivery["parts"]]
    source = folder / "build/Installer.generated.cs"
    source.parent.mkdir(exist_ok=True)
    source.write_text(template.replace("@@VERSION@@", version)
                      .replace("@@BASE_VERSION@@", delivery.get("runtime_version", version))
                      .replace("@@FULL_HASH@@", delivery["offline_sha256"])
                      .replace("@@FULL_SIZE@@", str(delivery["offline_bytes"]))
                      .replace("@@PARTS@@", ",\n".join(rows)), encoding="utf-8")
    compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    resources = (["/resource:" + str(application_update.resolve())
                  + ",MusicStudio.ApplicationUpdate.exe"] if application_update else [])
    subprocess.run([str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                    "/out:" + str(installer), "/reference:System.Windows.Forms.dll",
                    "/reference:System.Drawing.dll", "/reference:System.Net.Http.dll",
                    "/resource:" + str(wheel.resolve()) + ",MusicStudio.Update.whl",
                    "/win32icon:" + str(repo / "src/music_studio/ui/static/icon.ico"),
                    "/win32manifest:" + str(repo / "desktop/app.manifest"),
                    *resources, str(source)],
                   check=True)
    delivery.update(application_wheel=wheel.name, application_wheel_sha256=digest(wheel))
    if application_update:
        delivery.update(application_update=application_update.name,
                        application_update_sha256=digest(application_update))
    (folder / "DELIVERY.json").write_text(json.dumps(delivery, indent=2), encoding="utf-8")
    return [installer, *(folder / p["name"] for p in delivery["parts"]),
            folder / "DELIVERY.json"]


def write_checksums(folder, public):
    (folder / "SHA256SUMS.txt").write_text("".join(
        digest(path) + "  " + path.name + "\n" for path in public
    ), encoding="ascii")


def prepare_delivery(repo, installer, version, wheel=None):
    folder = installer.parent
    size = installer.stat().st_size
    checksum = digest(installer)
    public = [installer]
    if size >= ASSET_LIMIT:
        wheel = wheel or repo / "dist" / f"music_studio_local-{version}-py3-none-any.whl"
        if not wheel.is_file():
            raise ValueError("The matching application wheel is required for the online installer")
        parts = []
        with installer.open("rb") as source:
            index = 1
            while True:
                block = source.read(1024**2)
                if not block:
                    break
                path = folder / f"Music-Studio-{version}-Setup-x64-{index}.bin"
                hasher = hashlib.sha256()
                written = 0
                with path.open("wb") as output:
                    while block:
                        output.write(block)
                        hasher.update(block)
                        written += len(block)
                        if written == PART_SIZE:
                            break
                        block = source.read(min(1024**2, PART_SIZE - written))
                parts.append({"name": path.name, "size": written, "sha256": hasher.hexdigest()})
                index += 1
        assert sum(part["size"] for part in parts) == size
        offline = folder / "offline" / f"Music-Studio-{version}-Offline-Setup-x64.exe"
        offline.parent.mkdir(exist_ok=True)
        installer.replace(offline)
        delivery = {
            "version": version, "offline_installer": offline.name, "offline_bytes": size,
            "offline_sha256": checksum, "parts": parts,
        }
        public = build_bootstrap(repo, installer, version, delivery, wheel)
    write_checksums(folder, public)
    return public


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--rebuild-bootstrap", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.rebuild_bootstrap:
        if args.wheel is None:
            parser.error("--wheel is required to rebuild the bootstrap")
        installer = args.installer.resolve()
        metadata = json.loads((installer.parent / "DELIVERY.json").read_text(encoding="utf-8"))
        public = build_bootstrap(repo, installer, args.version, metadata, args.wheel)
        write_checksums(installer.parent, public)
    else:
        public = prepare_delivery(repo, args.installer.resolve(), args.version, args.wheel)
    for artifact in public:
        print(artifact.name, artifact.stat().st_size)
