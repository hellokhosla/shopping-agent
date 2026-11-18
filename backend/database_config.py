"""Load database settings from the environment file next to the backend code."""

import json
import os
from pathlib import Path

from dotenv import dotenv_values


def load_database_environment() -> None:
    for key, value in dotenv_values(Path(__file__).resolve().with_name(".env.local")).items():
        if value:
            os.environ.setdefault(key, value)


def catalog_conninfo() -> str:
    """Resolve the agent's database target without falling back to another database."""
    config_path = Path(__file__).resolve().with_name("database_target.json")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("Could not read backend/database_target.json.") from exc
    target = config.get("target") if isinstance(config, dict) else None
    if target == "local":
        from .local_postgres import local_conninfo

        return local_conninfo(config_path.with_name(".env.docker"))
    if target == "neon":
        load_database_environment()
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("Neon requires DATABASE_URL in the environment or backend/.env.local.")
        return url
    raise RuntimeError('Set "target" to "local" or "neon" in backend/database_target.json.')
