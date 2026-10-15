"""Download only the frozen VoiceBank-DEMAND pairs, verifying each WAV's SHA256."""

import argparse
import hashlib
import json
import re
import uuid
from pathlib import Path

from remotezip import RemoteZip
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SUITES = {
    "pilot": (
        "speech-cleanup-v1.json",
        "1efa1d8fa4e49ff0b25049f3c1cd08d052cc2d0c55ce74ea0b1e67bb1c5e88e5",
    ),
    "validation": (
        "speech-cleanup-validation-v1.json",
        "1c49f145356c51f181b9f1a14d7d1389f2d35cd4944c85f460fe1118902bdba3",
    ),
}


def download(output: Path, suite="all"):
    # Retry idempotent range requests; verified files are also reused across runs.
    with Session() as session:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        _download(output, suite, session)


def _download(output: Path, suite, session):
    root = Path(__file__).resolve().parents[1]
    samples, archives = {}, None
    for key in SUITES if suite == "all" else [suite]:
        filename, expected = SUITES[key]
        manifest_file = root / "benchmarks" / filename
        if hashlib.sha256(manifest_file.read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen speech manifest changed")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        archives = manifest["archives"]
        for sample in manifest["samples"]:
            if not re.fullmatch(r"p(?:232|257)_\d+", sample["id"]):
                raise ValueError("Invalid frozen sample ID")
            samples[sample["id"]] = sample
    for kind, url in archives.items():
        folder = output / kind
        folder.mkdir(parents=True, exist_ok=True)
        needed = []
        for sample in samples.values():
            path = folder / (sample["id"] + ".wav")
            if path.exists():
                if hashlib.sha256(path.read_bytes()).hexdigest() != sample[kind]["sha256"]:
                    raise ValueError(f"Existing file differs from the frozen sample: {path}")
            else:
                needed.append((sample, path))
        if not needed:
            continue
        with RemoteZip(url, session=session, timeout=45) as archive:
            for sample, path in needed:
                expected = sample[kind]
                if archive.getinfo(expected["member"]).file_size != expected["bytes"]:
                    raise ValueError("Dataset member size changed")
                data = archive.read(expected["member"])
                if (
                    len(data) != expected["bytes"]
                    or hashlib.sha256(data).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("Dataset member checksum changed")
                temporary = path.with_suffix("." + uuid.uuid4().hex + ".part")
                temporary.write_bytes(data)
                temporary.replace(path)
                print(kind + " " + sample["id"], flush=True)
    (output / "ATTRIBUTION.txt").write_text(
        "Cassia Valentini-Botinhao (2017), VoiceBank-DEMAND, University of Edinburgh/CSTR.\n"
        "https://doi.org/10.7488/ds/2117\nCC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n"
        "Original WAV bytes retained. This is a small frozen regression subset, "
        "not the full test set.\n",
        encoding="utf-8",
    )
    print(f"Verified {len(samples)} clean/noisy pairs. Audio is stored only in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".cache/benchmarks/speech-cleanup"))
    parser.add_argument("--suite", choices=["all", *SUITES], default="all")
    args = parser.parse_args()
    download(args.output, args.suite)
