# Local PostgreSQL database setup

Each teammate can create a separate PostgreSQL database on their own computer.
No shared Neon credentials are required. The setup includes pgvector, both retailer
catalogs, and locally generated product embeddings.

## 1. Install prerequisites

- Install Python 3.11 or newer.
- Install and start Docker Desktop. On Windows, use Linux containers.
- Install Git.
- Have an internet connection and several gigabytes of free disk space for the
  Docker images, embedding model, database, and vector index.

Docker Desktop and Python must be installed before running the setup script.

## 2. Get the code after the PR is merged

For an existing checkout, save or commit any unrelated changes first, then run:

```shell
git switch main
git pull --ff-only origin main
```

For a new checkout:

```shell
git clone https://github.com/hellokhosla/shopping-agent.git
cd shopping-agent
```

Run the remaining commands from the repository root, not from inside `backend`.
Before the PR is merged, use `git switch feat/local-pgvector` instead.

## 3. Create and load the database

Windows PowerShell:

```powershell
python backend\setup_local_database.py setup
```

macOS:

```bash
python3 backend/setup_local_database.py setup
```

The script:

1. Creates an isolated Python environment and installs the required packages.
2. Downloads and starts PostgreSQL 16 with pgvector and Ollama containers.
3. Creates local credentials in the git-ignored `backend/.env.docker`.
4. Applies the same schema used for Neon and loads Nordstrom and CALPAK catalogs.
5. Downloads the `bge-large` embedding model and generates 1,024-dimensional vectors.

Full embedding generation on a CPU can take many hours. Progress is committed in
batches. If interrupted, rerun setup or use the `embed` command below to resume.
Once the catalog load has completed, ordinary database queries can run while the
embedding backfill continues.

This does not change the shared Neon database or its connection settings.
Each computer has its own data, password, and Docker volumes.

## 4. Connect using DBeaver or pgAdmin

Create a PostgreSQL connection with:

| Setting | Value |
|---|---|
| Host | `127.0.0.1` |
| Port | `55432` |
| Database | `retail_catalog` |
| Username | `retail_local` |
| Password | `POSTGRES_PASSWORD` from `backend/.env.docker` |
| SSL | Disabled |

Use the password generated on your own computer, not someone else's.
Do not commit, paste into chat, or share `backend/.env.docker`.

To confirm the catalog is loaded, run:

```sql
SELECT retailer_id, count(*) AS active_products, count(embedding) AS embedded_products
FROM products
WHERE is_active
GROUP BY retailer_id
ORDER BY retailer_id;
```

For the included snapshot, expect 121,839 Nordstrom products and 171 CALPAK
products. Embedding counts increase until the backfill finishes.

## 5. Let the agent use the local database

[`database_target.json`](./database_target.json) defaults to:

```json
{
  "target": "local"
}
```

The agent reads the local Docker credentials from `backend/.env.docker`.
It does not fall back to Neon if the local connection fails.

The LLM steps still use OpenAI, independently of the database selection.
To run those steps, install the agent dependencies using your Python environment:

```powershell
python -m pip install -r backend\requirements.txt
```

On macOS, use `python3 -m pip install -r backend/requirements.txt`.
Create a git-ignored `backend/.env` in this same checkout:

```dotenv
OPENAI_API_KEY=your_own_api_key_here
```

Never commit a real key. OpenAI calls may incur charges.
Then run from the repository root:

```powershell
python -m backend.agent_graph 'Navy blazer under $150 in size M' --retailer nordstrom
```

On macOS, use `python3` instead of `python`.
The graph currently uses exact and lexical catalog search; selecting the local
database does not automatically enable vector ranking.

To switch the agent to Neon, change the target to `neon` and configure
`DATABASE_URL` in the process environment or `backend/.env.local`.
The database loader and shared-database test client are not controlled by this
target switch.

## 6. Check progress, resume, or stop

Windows PowerShell:

```powershell
python backend\setup_local_database.py status
python backend\setup_local_database.py embed --batch-size 8
python backend\setup_local_database.py stop
```

macOS:

```bash
python3 backend/setup_local_database.py status
python3 backend/setup_local_database.py embed --batch-size 8
python3 backend/setup_local_database.py stop
```

Stopping retains the database and downloaded model. Run `setup` again to start
the services and resume work. Do not remove the Compose volumes unless you intend
to permanently delete their local data.

## Troubleshooting

- **Docker Engine is not running:** Start Docker Desktop, wait until it is ready,
  and rerun setup.
- **Port already in use:** Free the required ports (`55432` for PostgreSQL and
  `11434` for Ollama), or change `POSTGRES_PORT` in `backend/.env.docker` before
  rerunning setup. Use the same PostgreSQL port in your database client.
- **Password authentication failed:** Use the password originally generated for
  the existing Docker database volume. Editing `POSTGRES_PASSWORD` does not
  change a password in an already initialized database.
- **Missing local credentials:** Run setup from this checkout. If another
  checkout on the same machine already created the Docker database, securely
  copy its generated `.env.docker` into this checkout's `backend` folder.
- **Missing OpenAI credentials:** Put `OPENAI_API_KEY` in `backend/.env` in the
  checkout actually running the agent, not in another project copy.
- **Corporate certificate error:** If Ollama reports
  `x509: certificate signed by unknown authority`, follow the approved CA
  instructions in the [backend README](./README.md#local-docker-postgresql-and-vector-embeddings).
  Do not disable TLS verification.
