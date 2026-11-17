"""Load database environment files without blank templates masking credentials."""

import os
from pathlib import Path

from dotenv import dotenv_values


def load_nonempty_dotenv(path: str | Path) -> None:
    for key, value in dotenv_values(path).items():
        if value:
            os.environ.setdefault(key, value)
