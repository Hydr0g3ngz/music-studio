"""Build wheel/sdist and a Windows source+wheel preview ZIP, with SHA-256 sums."""

import argparse
import hashlib
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from music_studio import __version__


def package(root: Path, dist: Path, *, build=True):
    dist.mkdir(parents=True, exist_ok=True)
    if build:
        subprocess.run([sys.executable, "-m", "build", "--outdir", str(dist)], cwd=root, check=True)
    wheel = dist / f"music_studio_local-{__version__}-py3-none-any.whl"
    source = dist / f"music_studio_local-{__version__}.tar.gz"
    archive = dist / f"Music-Studio-{__version__}-Windows.zip"
    prefix = f"Music-Studio-{__version__}"
    with tarfile.open(source) as tar, zipfile.ZipFile(
        archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as output:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = PurePosixPath(*PurePosixPath(member.name).parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unexpected source archive member: {member.name}")
            data = tar.extractfile(member).read()
            output.writestr(f"{prefix}/{relative}", data)
        output.write(wheel, f"{prefix}/packages/{wheel.name}")
    for required in ("Start-Music-Studio.cmd", "QUICKSTART.md", "scripts/launch.ps1"):
        with zipfile.ZipFile(archive) as output:
            if f"{prefix}/{required}" not in output.namelist():
                raise ValueError(f"Release is missing {required}")
    files = [archive, wheel, source]
    checksums = dist / "SHA256SUMS.txt"
    checksums.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
        ),
        encoding="ascii", newline="\n",
    )
    print("Built release (Python required; neural weights not bundled):")
    for path in [*files, checksums]:
        print(f"  {path.name}  {path.stat().st_size:,} bytes")
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package(root, args.dist.resolve(), build=not args.skip_build)
