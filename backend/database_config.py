"""Load database settings from the environment file next to the backend code."""

import os
from pathlib import Path

from dotenv import dotenv_values


def load_database_environment() -> None:
    for key, value in dotenv_values(Path(__file__).resolve().with_name(".env.local")).items():
        if value:
            os.environ.setdefault(key, value)
