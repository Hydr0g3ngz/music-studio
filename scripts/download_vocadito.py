"""Fetch the public vocadito record and verify it before extracting benchmark files."""

import argparse
import hashlib
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/api/records/5578807/files/vocadito.zip/content"
SHA256 = "e0d6b99d3f9c594afe5ae5c4d7bdacebe569e53b809e90b89d1c771c4f9990e3"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(destination: Path):
    root = destination.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "vocadito.zip"
    with tempfile.TemporaryDirectory(prefix="vocadito-", dir=root) as temporary:
        temporary = Path(temporary)
        if not archive.exists():
            incoming = temporary / "download.zip"
            with urllib.request.urlopen(URL, timeout=60) as response, incoming.open("wb") as output:
                shutil.copyfileobj(response, output)
            if digest(incoming) != SHA256:
                raise ValueError("Downloaded archive failed the frozen SHA256 check")
            incoming.replace(archive)
        if digest(archive) != SHA256:
            raise ValueError(
                "Existing archive differs from the frozen record; choose a new directory"
            )
        count = 0
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                if entry.is_dir() or entry.filename.startswith("__MACOSX/"):
                    continue
                target = (root / entry.filename).resolve()
                if not target.is_relative_to(root):
                    raise ValueError("Archive path escapes the dataset directory")
                incoming = temporary / "entry"
                with source.open(entry) as audio, incoming.open("wb") as output:
                    shutil.copyfileobj(audio, output)
                if target.exists():
                    if digest(target) != digest(incoming):
                        raise ValueError(
                            f"Refusing to overwrite modified benchmark data: {entry.filename}"
                        )
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    incoming.replace(target)
                count += 1
    print(f"Verified {count} files in {root}")
    print("vocadito: Bittner, Pasalo, Bosch, Meseguer Brocal & Rubinstein (2021), CC BY 4.0")
    print("Source: https://zenodo.org/records/5578807")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(".artifacts/benchmark/vocadito"))
    args = parser.parse_args()
    download(args.data)


if __name__ == "__main__":
    main()
