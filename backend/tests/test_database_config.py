import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database_config import load_nonempty_dotenv


class DatabaseConfigTests(unittest.TestCase):
    def test_blank_template_allows_ignored_env_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / ".env.local").write_text("DATABASE_URL=\n", encoding="utf-8")
            (root / ".env").write_text("DATABASE_URL=example-from-env\n", encoding="utf-8")
            load_nonempty_dotenv(root / ".env.local")
            load_nonempty_dotenv(root / ".env")
            self.assertEqual(os.environ["DATABASE_URL"], "example-from-env")

    def test_process_then_local_then_env_precedence_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DATABASE_URL": "process-value"}, clear=True
        ):
            root = Path(directory)
            (root / ".env.local").write_text(
                "DATABASE_URL=local-value\nDATABASE_URL_UNPOOLED=local-direct\n", encoding="utf-8"
            )
            (root / ".env").write_text(
                "DATABASE_URL=env-value\nDATABASE_URL_UNPOOLED=env-direct\n", encoding="utf-8"
            )
            load_nonempty_dotenv(root / ".env.local")
            load_nonempty_dotenv(root / ".env")
            self.assertEqual(os.environ["DATABASE_URL"], "process-value")
            self.assertEqual(os.environ["DATABASE_URL_UNPOOLED"], "local-direct")


if __name__ == "__main__":
    unittest.main()
