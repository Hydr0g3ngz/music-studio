"""Explicit optional Mel-Band RoFormer setup; core startup remains offline."""

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
import venv
import zipfile
from pathlib import Path

SOURCE = "6fdad13686bb7e84d029ec66f9dbe76e65c93ebf"
ARCHIVE_SHA256 = "fa62b1ff7602e1dcaef1234274ad0ca4eafbea4c7c02554b1b8b5c64544cee9d"
MODEL = "ac9b0614ab3cd7f77219e18ba494dfd93956c348"
WEIGHT_SHA256 = "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url, path, expected):
    if not path.is_file() or digest(path) != expected:
        partial = path.with_suffix(".part")
        print("Downloading " + path.name, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        if digest(partial) != expected:
            raise RuntimeError("Download checksum mismatch: " + path.name)
        partial.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".artifacts/roformer"))
    parser.add_argument(
        "--runtime-python", type=Path, help="Use a prepared Python without installing packages"
    )
    parser.add_argument("--torch-index-url", default="https://download.pytorch.org/whl/cu124")
    parser.add_argument("--config", type=Path, default=Path(".artifacts/separation-runtime.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.runtime_python:
        python = args.runtime_python.resolve()
    else:
        env = root / "env"
        venv.EnvBuilder(with_pip=True).create(env)
        python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "torch==2.5.1",
                "--index-url",
                args.torch_index_url,
            ],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "numpy==1.26.4",
                "soundfile==0.13.1",
                "librosa==0.11.0",
                "PyYAML==6.0.2",
                "ml-collections==1.1.0",
                "beartype==0.18.5",
                "einops==0.8.1",
                "rotary-embedding-torch==0.8.9",
                "matplotlib==3.10.3",
                "tqdm==4.67.1",
                "pydantic>=2,<3",
                "platformdirs>=4",
            ],
            check=True,
        )
    archive = root / "source.zip"
    download(
        f"https://codeload.github.com/ZFTurbo/Music-Source-Separation-Training/zip/{SOURCE}",
        archive,
        ARCHIVE_SHA256,
    )
    with zipfile.ZipFile(archive) as package:
        prefix = f"Music-Source-Separation-Training-{SOURCE}/"
        for name in package.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = Path(name[len(prefix) :])
            if relative.parts[0] not in ("models", "utils", "configs", "LICENSE"):
                continue
            target = (root / "source" / relative).resolve()
            if not target.is_relative_to(root / "source"):
                raise RuntimeError("Invalid source path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(name))
    profile = root / "source/configs/KimberleyJensen/config_vocals_mel_band_roformer_kj.yaml"
    (root / "profile.yaml").write_bytes(profile.read_bytes())
    download(
        f"https://huggingface.co/KimberleyJSN/melbandroformer/resolve/{MODEL}/MelBandRoformer.ckpt",
        root / "MelBandRoformer.ckpt",
        WEIGHT_SHA256,
    )
    subprocess.run(
        [
            str(python),
            "-c",
            "import torch, numpy, soundfile, librosa, yaml, ml_collections, beartype; "
            "import einops, rotary_embedding_torch, matplotlib, pydantic, platformdirs",
        ],
        check=True,
    )
    files = [
        root / "profile.yaml",
        root / "MelBandRoformer.ckpt",
        *sorted((root / "source").rglob("*.py")),
    ]
    config = {
        "python": str(python),
        "root": str(root),
        "source_revision": SOURCE,
        "model_revision": MODEL,
        "files": [{"file": p.relative_to(root).as_posix(), "sha256": digest(p)} for p in files],
    }
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Configured local separation: " + str(args.config.resolve()))


if __name__ == "__main__":
    main()
