"""Independent desktop controller for the song-analysis application."""

import argparse
import hashlib
import json
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from filelock import FileLock, Timeout
from platformdirs import user_data_path

from .config import Settings


def identity(workspace):
    return hashlib.sha256(os.path.normcase(str(Path(workspace).resolve())).encode()).hexdigest()


def emit(**value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def probe(url, workspace):
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.username or parsed.password or parsed.path or parsed.query
                or parsed.fragment or not parsed.port or not 1024 <= parsed.port <= 65535):
            return False
        http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with http.open(url + "/api/instance", timeout=1) as response:
            value = json.load(response)
        return value.get("product") == "music-studio" and value.get("workspace") == identity(
            workspace
        )
    except (OSError, ValueError, TypeError):
        return False


def run(workspace, port=8765, controller=False):
    import uvicorn

    from .io import read_json, write_json
    from .ui.server import create_app

    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(workspace / ".music-studio-server.lock"), timeout=0)
    descriptor = workspace / ".music-studio-instance.json"
    try:
        lock.acquire()
    except Timeout:
        for _ in range(60):
            try:
                saved = read_json(descriptor)
                if probe(saved["url"], workspace):
                    emit(state="ready", url=saved["url"] + "/", reused=True)
                    return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.25)
        raise RuntimeError("Music Studio is starting. Please retry in a few seconds.") from None
    server = None
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not 1024 <= port <= 65535:
            raise ValueError("Port must be between 1024 and 65535")
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        settings = Settings(offline=True)
        bundled = Path(sys.executable).resolve().parent.parent / "models"
        if (bundled / "BUNDLED-MODELS.json").is_file():
            profile = read_json(bundled / "BUNDLED-MODELS.json")["profile"]
            os.environ["MUSIC_STUDIO_BUNDLED_PROFILE"] = profile
            settings = Settings(model_dir=str(bundled),
                                device="cpu" if profile == "cpu-small" else "auto", offline=True)
        server = uvicorn.Server(uvicorn.Config(
            create_app(workspace, settings), host="127.0.0.1", access_log=False,
        ))
        thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while thread.is_alive() and time.monotonic() < deadline:
            if server.started and probe(url, workspace):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Could not start Music Studio. Check the desktop log.")
        write_json(descriptor, {"url": url, "pid": os.getpid()})
        emit(state="ready", url=url + "/", reused=False)
        if controller:
            for line in sys.stdin:
                if line.strip() == "quit":
                    break
            server.should_exit = True
        try:
            while thread.is_alive():
                thread.join(0.25)
        except KeyboardInterrupt:
            server.should_exit = True
            thread.join(30)
    finally:
        if server:
            server.should_exit = True
        listener.close()
        lock.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path,
                        default=user_data_path("MusicStudio", appauthor=False) / "Songs")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--controller", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        run(args.workspace, args.port, args.controller)
    except Exception as error:
        emit(state="error", message=str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
