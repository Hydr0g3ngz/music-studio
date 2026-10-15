"""Small atomic progress records shared by model workers and the local UI."""

import time
from pathlib import Path

from .io import write_json


def report_progress(config, label, completed, total, *, unit="段"):
    path = config.get("_progress_path")
    if path:
        write_json(
            Path(path),
            {
                "label": label,
                "completed": completed,
                "total": total,
                "unit": unit,
                "updated_at": time.time(),
            },
        )
