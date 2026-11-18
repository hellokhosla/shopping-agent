from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.local_database import (
    build_database_url,
    ensure_local_env,
    format_vector,
)


class LocalDatabaseTests(unittest.TestCase):
    def test_local_env_is_created_once_and_preserves_existing_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env.docker"

            first = ensure_local_env(env_path)
            second = ensure_local_env(env_path)

            self.assertEqual(first["POSTGRES_PASSWORD"], second["POSTGRES_PASSWORD"])
            self.assertEqual(first["POSTGRES_PORT"], "55432")
            self.assertNotIn("DATABASE_URL", first)

    def test_database_url_escapes_password_and_uses_local_host(self) -> None:
        url = build_database_url("local@pass/word", "55433")

        self.assertEqual(
            url,
            "postgresql://retail_local:local%40pass%2Fword@127.0.0.1:55433/retail_catalog",
        )

    def test_vector_requires_schema_dimensions_and_finite_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires 1024"):
            format_vector([0.1])

        with self.assertRaisesRegex(ValueError, "non-numeric or non-finite"):
            format_vector([float("nan")] * 1024)

        with self.assertRaisesRegex(ValueError, "non-numeric or non-finite"):
            format_vector(["invalid"] * 1024)

        self.assertTrue(format_vector([0.0] * 1024).startswith("[0.0,"))

    def test_invalid_local_port_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env.docker"
            env_path.write_text(
                "POSTGRES_PASSWORD=local-only\nPOSTGRES_PORT=80\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "POSTGRES_PORT"):
                ensure_local_env(env_path)


if __name__ == "__main__":
    unittest.main()
