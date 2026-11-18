"""Manage a local pgvector catalog and resumable Ollama embedding backfill."""

from __future__ import annotations

import argparse
import json
import math
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
COMPOSE_FILE = BACKEND_DIR / "docker-compose.local.yml"
ENV_FILE = BACKEND_DIR / ".env.docker"
MODEL = "bge-large"
MODEL_ID = f"ollama:{MODEL}"
EMBEDDING_DIMENSIONS = 1024
DEFAULT_BATCH_SIZE = 16
OLLAMA_BASE_URL = "http://127.0.0.1:11434"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def ensure_local_env(path: Path = ENV_FILE) -> dict[str, str]:
    """Create local-only credentials without reading or changing .env.local."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        contents = (
            "# Local Docker database credentials. Do not copy Neon credentials here.\n"
            f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n"
            "POSTGRES_PORT=55432\n"
        )
        try:
            with path.open("x", encoding="utf-8", newline="\n") as env_file:
                env_file.write(contents)
        except FileExistsError:
            pass

    values = _read_env_file(path)
    if not values.get("POSTGRES_PASSWORD"):
        raise ValueError(f"{path} must contain a non-empty POSTGRES_PASSWORD.")
    port = values.get("POSTGRES_PORT", "55432")
    if not port.isdecimal() or not 1024 <= int(port) <= 65535:
        raise ValueError("POSTGRES_PORT must be an integer between 1024 and 65535.")
    values["POSTGRES_PORT"] = port
    return values


def build_database_url(password: str, port: str = "55432") -> str:
    return (
        f"postgresql://retail_local:{quote(password, safe='')}"
        f"@127.0.0.1:{port}/retail_catalog"
    )


def compose_command(*arguments: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        *arguments,
    ]


def format_vector(embedding: list[float]) -> str:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Embedding model returned {len(embedding)} dimensions; "
            f"the database schema requires {EMBEDDING_DIMENSIONS}."
        )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in embedding
    ):
        raise ValueError("Embedding model returned a non-numeric or non-finite value.")
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


def _run_compose(*arguments: str) -> None:
    subprocess.run(
        compose_command(*arguments),
        cwd=PROJECT_ROOT,
        check=True,
    )


def _connect(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "The local environment is missing psycopg; rerun the setup script."
        ) from exc
    return psycopg.connect(database_url, connect_timeout=5, autocommit=True)


def _wait_for_postgres(database_url: str, timeout_seconds: int = 300) -> None:
    from psycopg import OperationalError

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with _connect(database_url) as connection:
                connection.execute("SELECT 1")
            print("Local PostgreSQL is ready.")
            return
        except OperationalError:
            time.sleep(2)
    raise TimeoutError(
        "Local PostgreSQL did not become ready. Check Docker Desktop and run "
        "`python -m backend.local_database status` for details."
    )


def _ollama_request(path: str, payload: dict[str, object] | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{OLLAMA_BASE_URL}{path}", data=data, headers=headers)
    try:
        with urlopen(request, timeout=900 if path == "/api/embed" else 10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Ollama returned HTTP {exc.code}: {details}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Could not reach the local Ollama service at "
            f"{OLLAMA_BASE_URL}. Start it with `python -m backend.local_database setup`."
        ) from exc


def _wait_for_ollama(timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            _ollama_request("/api/tags")
            return
        except RuntimeError:
            time.sleep(2)
    raise TimeoutError("The local Ollama service did not become ready.")


def _pull_model() -> None:
    if any(
        entry.get("name") == f"{MODEL}:latest"
        for entry in _ollama_request("/api/tags").get("models", [])
    ):
        print(f"Using the cached local embedding model ({MODEL}).")
        return
    print(f"Downloading the local embedding model ({MODEL}); this may take a few minutes.")
    _run_compose("exec", "-T", "ollama", "ollama", "pull", MODEL)


def _load_catalog(database_url: str) -> None:
    from backend.database_loader import load_batches, prepare_all_batches

    batches = prepare_all_batches()
    for batch in batches:
        print(
            f"Prepared {batch.retailer_id}: {len(batch.products):,} products, "
            f"{len(batch.variants):,} variants"
        )
    # Pass the local URL explicitly; this path never loads backend/.env.local.
    load_batches(batches, database_url)
    print("Local schema and catalog load completed.")


def _active_embedding_counts(connection) -> tuple[int, int, int]:
    row = connection.execute(
        """
        SELECT count(*) FILTER (WHERE embedding IS NULL),
               count(*) FILTER (WHERE embedding IS NOT NULL AND embedding_model = %s),
               count(*) FILTER (WHERE embedding IS NOT NULL
                                AND embedding_model IS DISTINCT FROM %s)
        FROM products
        WHERE is_active
        """,
        (MODEL_ID, MODEL_ID),
    ).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


def _embed_batch(texts: list[str]) -> list[list[float]]:
    result = _ollama_request(
        "/api/embed",
        {"model": MODEL, "input": texts, "truncate": True},
    )
    embeddings = result.get("embeddings")
    if (
        not isinstance(embeddings, list)
        or len(embeddings) != len(texts)
        or any(not isinstance(embedding, list) for embedding in embeddings)
    ):
        raise RuntimeError("Ollama returned an unexpected embedding response.")
    return embeddings


def backfill_embeddings(
    database_url: str,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    reembed: bool = False,
) -> None:
    if not 1 <= batch_size <= 128:
        raise ValueError("--batch-size must be between 1 and 128.")

    with _connect(database_url) as connection:
        if reembed:
            print("Clearing local embeddings so all active products can be re-embedded.")
            connection.execute(
                """
                UPDATE products
                SET embedding = NULL, embedding_model = NULL, embedded_at = NULL
                WHERE is_active
                """
            )
        pending, embedded, mismatched = _active_embedding_counts(connection)
        if mismatched:
            raise RuntimeError(
                f"{mismatched:,} active products have vectors from another model. "
                "Use --reembed to rebuild local vectors with the configured model."
            )
        if pending == 0:
            print(f"All {embedded:,} active products already use {MODEL_ID}.")
            return

        print(
            f"Embedding {pending:,} active products with {MODEL_ID}; "
            f"{embedded:,} already complete."
        )
        completed = 0
        while True:
            with connection.transaction():
                rows = connection.execute(
                    """
                    SELECT product_id, search_text
                    FROM products
                    WHERE is_active AND embedding IS NULL
                    ORDER BY product_id
                    LIMIT %s
                    """,
                    (batch_size,),
                ).fetchall()
            if not rows:
                break

            vectors = _embed_batch([row[1] for row in rows])
            updates = [
                (format_vector(vector), MODEL_ID, row[0])
                for row, vector in zip(rows, vectors, strict=True)
            ]
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE products
                    SET embedding = %s::vector,
                        embedding_model = %s,
                        embedded_at = now()
                    WHERE product_id = %s
                      AND is_active
                      AND embedding IS NULL
                    """,
                    updates,
                )
            completed += len(updates)
            print(f"Embedded {completed:,} / {pending:,} pending products.")

        print(f"Embedding backfill complete. Model: {MODEL_ID}.")


def _status(database_url: str) -> None:
    with _connect(database_url) as connection:
        active = connection.execute(
            "SELECT count(*) FROM products WHERE is_active"
        ).fetchone()[0]
        pending, embedded, mismatched = _active_embedding_counts(connection)
    print(f"Active products: {active:,}")
    print(f"Embedded with {MODEL_ID}: {embedded:,}")
    print(f"Pending embeddings: {pending:,}")
    if mismatched:
        print(f"Vectors from another model: {mismatched:,} (run embed --reembed to replace).")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up and maintain the isolated local pgvector retail catalog."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "setup",
        help="Pull and start local services, load the shared schema/catalog, and embed products.",
    )
    subparsers.add_parser("status", help="Show local catalog and embedding progress.")
    embed_parser = subparsers.add_parser(
        "embed", help="Resume embedding active products that do not yet have vectors."
    )
    embed_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    embed_parser.add_argument(
        "--reembed",
        action="store_true",
        help="Clear and rebuild vectors for active products in the local database only.",
    )
    subparsers.add_parser(
        "stop",
        help="Stop local containers without deleting catalog data or downloaded models.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        values = ensure_local_env()
        database_url = build_database_url(values["POSTGRES_PASSWORD"], values["POSTGRES_PORT"])

        if args.command == "setup":
            print("Downloading local PostgreSQL/pgvector and Ollama container images.")
            _run_compose("pull")
            _run_compose("up", "-d")
            _wait_for_postgres(database_url)
            _load_catalog(database_url)
            _wait_for_ollama()
            _pull_model()
            backfill_embeddings(database_url)
        elif args.command == "status":
            _status(database_url)
        elif args.command == "embed":
            _wait_for_ollama()
            backfill_embeddings(
                database_url,
                batch_size=args.batch_size,
                reembed=args.reembed,
            )
        elif args.command == "stop":
            _run_compose("stop")
            print("Local containers stopped. Volumes and model downloads are retained.")
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Local database operation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
