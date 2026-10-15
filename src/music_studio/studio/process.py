"""Own and stop only the process tree created for a local task."""

import os
import signal
import subprocess
import time
from pathlib import Path


class TaskStopped(RuntimeError):
    pass


def stop_owned_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Windows venv python.exe is a proxy: stopping just it leaves the real worker alive.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)


def run_owned(arguments, log_path: Path, environment, *, cancelled=lambda: False, timeout=7200):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
        )
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled():
                    raise TaskStopped("Task cancelled")
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"Local task exceeded {timeout}s")
                time.sleep(0.1)
            return process.returncode
        except BaseException:
            stop_owned_process(process)
            raise


def log_tail(path: Path, length=4000):
    if not path.is_file():
        return ""
    with path.open("rb") as file:
        file.seek(max(0, path.stat().st_size - length))
        return file.read(length).decode("utf-8", errors="replace")
