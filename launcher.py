"""Start the frontend and Python backend together for local development."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def command(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"{name} is not installed or is not on PATH")
    return resolved


def main() -> int:
    npm = command("npm.cmd" if os.name == "nt" else "npm")
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--reload",
        ],
        cwd=ROOT / "backend",
    )
    frontend = subprocess.Popen(
        [npm, "run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"],
        cwd=ROOT,
    )

    processes = [backend, frontend]

    def stop(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    print("\nLinguaBridge is starting:")
    print("  Dashboard: http://localhost:3000")
    print("  Backend:   http://localhost:8000")
    print("  API docs:  http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop both services.\n")

    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.4)
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return next((process.returncode or 0 for process in processes if process.returncode), 0)


if __name__ == "__main__":
    raise SystemExit(main())
