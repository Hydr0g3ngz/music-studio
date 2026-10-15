"""Pinned optional Beat This checkpoints from the authors' public cloud."""

import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

SPECS = {
    "small0": (
        8451101,
        "sha256",
        "6074be2c4d490c5f6101fcc374a1ec72ae93456e23bb6019783b849f5dc7d47b",
    ),
    "final0": (81058141, "sha1", "e1506282faf66ca10e8ab50ee26bd542b7b9ff0a"),
    "fold2": (81054590, "sha1", "9086646abda3986fc5e335f719aed5123274adb4"),
    "fold3": (81054590, "sha1", "cda098b18ddf85c2ee420f75e40d4e2d18adba39"),
    "fold4": (81054590, "sha1", "587b29ef04f7e4eacaca3676d6cca0db74a87866"),
    "fold6": (81054590, "sha1", "9ea3bf2e22722392c393a92fb63157d94fd32ece"),
}
BASE_URL = "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp"


def verified(path: Path, spec) -> bool:
    size, algorithm, expected = spec
    if not path.is_file() or path.stat().st_size != size:
        return False
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == expected


def beat_checkpoint(config: dict) -> Path:
    name = config["rhythm_checkpoint"]
    if name not in SPECS:
        raise ValueError(f"No pinned Beat This checkpoint: {name}")
    spec = SPECS[name]
    path = Path(config["model_dir"]) / "beat_this" / f"{name}.ckpt"
    if path.exists():
        if verified(path, spec):
            return path
        raise RuntimeError(f"Beat This checksum mismatch: {path}")
    if config["offline"]:
        raise RuntimeError(
            "Beat This model missing offline; run models download --rhythm-backend beat_this first."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".ckpt.part")
    offset = part.stat().st_size if part.exists() else 0
    if offset >= spec[0]:
        if verified(part, spec):
            part.replace(path)
            return path
        offset = 0
    headers = {"User-Agent": "MusicStudio-models/0.1"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    with urlopen(Request(f"{BASE_URL}/{name}.ckpt", headers=headers), timeout=30) as response:
        if offset and response.status != 206:
            offset = 0
        if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise RuntimeError("Model download returned an unexpected byte range")
        with part.open("ab" if offset else "wb") as output:
            while block := response.read(262144):
                output.write(block)
                if output.tell() > spec[0]:
                    raise RuntimeError("Model download exceeds pinned size")
    if not verified(part, spec):
        raise RuntimeError("Model download failed its pinned checksum; rerun to resume")
    part.replace(path)
    return path
