import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from psycopg.conninfo import conninfo_to_dict

from backend.database_config import catalog_conninfo, load_database_environment


class DatabaseConfigTests(unittest.TestCase):
    def test_local_target_uses_docker_settings_even_with_cloud_url_in_environment(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DATABASE_URL": "cloud-value", "PGHOSTADDR": "192.0.2.1"}, clear=True
        ):
            root = Path(directory)
            (root / "database_target.json").write_text('{"target":"local"}', encoding="utf-8")
            (root / ".env.docker").write_text(
                "POSTGRES_PASSWORD='test@local/password'\nPOSTGRES_PORT=55433\n", encoding="utf-8"
            )
            with patch("backend.database_config.__file__", str(root / "database_config.py")):
                options = conninfo_to_dict(catalog_conninfo())
            self.assertEqual(options["hostaddr"], "127.0.0.1")
            self.assertEqual(options["port"], "55433")
            self.assertEqual(options["dbname"], "retail_catalog")
            self.assertEqual(options["password"], "test@local/password")
            self.assertEqual(os.environ["DATABASE_URL"], "cloud-value")

    def test_neon_target_preserves_existing_database_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            (root / "database_target.json").write_text('{"target":"neon"}', encoding="utf-8")
            (root / ".env.local").write_text("DATABASE_URL=neon-value\n", encoding="utf-8")
            with patch("backend.database_config.__file__", str(root / "database_config.py")):
                self.assertEqual(catalog_conninfo(), "neon-value")

    def test_invalid_or_unconfigured_local_target_never_falls_back_to_neon(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DATABASE_URL": "cloud-value"}, clear=True
        ):
            root = Path(directory)
            config = root / "database_target.json"
            with patch("backend.database_config.__file__", str(root / "database_config.py")):
                config.write_text('{"target":"typo"}', encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, 'Set "target"'):
                    catalog_conninfo()
                config.write_text('{"target":"local"}', encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "POSTGRES_PASSWORD"):
                    catalog_conninfo()

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
