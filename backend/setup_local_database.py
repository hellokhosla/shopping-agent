"""Bootstrap an isolated Python environment and run the local database workflow."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
VENV_DIR = BACKEND_DIR / ".venv-local-db"
REQUIREMENTS = BACKEND_DIR / "requirements-local.txt"


def _environment_python() -> Path:
    executable = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not executable.exists():
        print(f"Creating an isolated Python environment at {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
        result = subprocess.run(
            [str(executable), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("Could not install local database Python dependencies.")
    return executable


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required. Install it, then rerun this script.")
        return 2
    if shutil.which("docker") is None:
        print(
            "Docker CLI was not found. Install Docker Desktop for Windows or macOS, "
            "start it, and rerun this script."
        )
        return 2
    engine = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if engine.returncode:
        print(
            "Docker Engine is not running. Start Docker Desktop, wait until it is ready, "
            "and rerun this script."
        )
        return 2

    try:
        executable = _environment_python()
    except RuntimeError as exc:
        print(exc)
        return 2

    result = subprocess.run(
        [str(executable), "-u", "-m", "backend.local_database", *sys.argv[1:]],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
