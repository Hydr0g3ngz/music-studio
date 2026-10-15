"""Fetch pinned official files with resumable HTTP ranges and SHA-256 verification."""

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from music_studio.lyric_models import MODELS


def fetch(url, headers=None, limit=None):
    with urlopen(Request(url, headers=headers or {}), timeout=90) as response:
        if headers and "Range" in headers and response.status != 206:
            raise ValueError("Server did not honor the requested byte range")
        return response.read(limit + 1 if limit is not None else -1), response.headers


def download(name, root, workers=8):
    repo, revision = MODELS[name]
    metadata, _ = fetch(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true")
    metadata = json.loads(metadata)
    if metadata["sha"] != revision:
        raise ValueError("Model revision changed")
    folder = root / "lyrics" / name / revision
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for item in metadata["siblings"]:
        filename = item["rfilename"]
        if not filename.endswith((".json", ".txt", ".safetensors")):
            continue
        path = (folder / filename).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError("Invalid model file path")
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}?download=true"
        lfs = item.get("lfs")
        if lfs:
            size, expected = lfs["size"], lfs["sha256"]
            if not path.exists() or path.stat().st_size != size:
                parts = folder / ".parts" / expected
                parts.mkdir(parents=True, exist_ok=True)
                chunk = 8 * 1024 * 1024
                ranges = [(i, min(size, i + chunk)) for i in range(0, size, chunk)]

                def part(bounds, parts=parts, url=url):
                    start, end = bounds
                    target = parts / str(start)
                    if target.exists() and target.stat().st_size == end - start:
                        return target
                    for attempt in range(4):
                        try:
                            data, headers = fetch(
                                url, {"Range": f"bytes={start}-{end - 1}"}, end - start
                            )
                            if len(data) != end - start or not headers.get(
                                "Content-Range", ""
                            ).startswith(f"bytes {start}-{end - 1}/"):
                                raise ValueError("Unexpected HTTP range")
                            temporary = target.with_suffix(".tmp")
                            temporary.write_bytes(data)
                            temporary.replace(target)
                            return target
                        except Exception:
                            if attempt == 3:
                                raise
                            time.sleep(attempt + 1)

                print(f"{name}/{filename}: {size / 1024**3:.2f} GiB", flush=True)
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    for index, _ in enumerate(pool.map(part, ranges), 1):
                        if index % 24 == 0 or index == len(ranges):
                            print(f"{name}: {index}/{len(ranges)} parts", flush=True)
                temporary = path.with_suffix(".download")
                with temporary.open("wb") as output:
                    for start, _ in ranges:
                        with (parts / str(start)).open("rb") as source:
                            while block := source.read(1024 * 1024):
                                output.write(block)
                temporary.replace(path)
            with path.open("rb") as weights:
                digest = hashlib.file_digest(weights, "sha256").hexdigest()
            if digest != expected:
                raise ValueError(f"Weight SHA-256 mismatch: {path}")
        else:
            if not path.exists():
                data, _ = fetch(url)
                temporary = path.with_suffix(path.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest[filename] = digest
    (folder / "model-ready.json").write_text(
        json.dumps({"repository": repo, "revision": revision, "sha256": manifest}, indent=2),
        encoding="utf-8",
    )
    print(f"Verified {name}@{revision}: {folder}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=MODELS, nargs="+", default=list(MODELS))
    parser.add_argument("--root", type=Path, default=Path(".cache/models"))
    parser.add_argument("--workers", type=int, default=8, choices=range(1, 25))
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    for name in args.model:
        download(name, args.root.resolve(), args.workers)
