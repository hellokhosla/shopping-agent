import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database_config import load_database_environment


class DatabaseConfigTests(unittest.TestCase):
    def test_reads_backend_file_without_loading_project_root_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            backend = root / "backend"
            backend.mkdir()
            (root / ".env.local").write_text(
                "DATABASE_URL=root-value\nROOT_ONLY=do-not-load\n", encoding="utf-8"
            )
            (root / ".env").write_text("ROOT_ENV_ONLY=do-not-load\n", encoding="utf-8")
            (backend / ".env.local").write_text("DATABASE_URL=backend-value\n", encoding="utf-8")
            with patch("backend.database_config.__file__", str(backend / "database_config.py")):
                load_database_environment()
            self.assertEqual(os.environ["DATABASE_URL"], "backend-value")
            self.assertNotIn("ROOT_ONLY", os.environ)
            self.assertNotIn("ROOT_ENV_ONLY", os.environ)

    def test_process_values_take_precedence_over_backend_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DATABASE_URL": "process-value"}, clear=True
        ):
            root = Path(directory)
            (root / ".env.local").write_text(
                "DATABASE_URL=local-value\nDATABASE_URL_UNPOOLED=local-direct\n", encoding="utf-8"
            )
            with patch("backend.database_config.__file__", str(root / "database_config.py")):
                load_database_environment()
            self.assertEqual(os.environ["DATABASE_URL"], "process-value")
            self.assertEqual(os.environ["DATABASE_URL_UNPOOLED"], "local-direct")

    def test_blank_template_does_not_add_empty_credentials_to_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / ".env.local").write_text(
                "DATABASE_URL=\nDATABASE_URL_UNPOOLED=\nNEON_BRANCH=production\n", encoding="utf-8"
            )
            with patch("backend.database_config.__file__", str(root / "database_config.py")):
                load_database_environment()
            self.assertNotIn("DATABASE_URL", os.environ)
            self.assertNotIn("DATABASE_URL_UNPOOLED", os.environ)
            self.assertEqual(os.environ["NEON_BRANCH"], "production")


if __name__ == "__main__":
    unittest.main()
