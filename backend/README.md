# Backend files and data enrichment

The retailer JSON config maps each retailer's source columns to common fields; the category pack supplies size
vocabularies. `catalog.py` uses these settings to clean and normalize source rows into shared `Product` records,
enrich colors, apply source or synthetic availability, and cache the result. Agent logic is not involved in this
pipeline.

### Core files

**`backend/configuration.py`**  
Validates retailer JSON files, field mappings, and category-pack size vocabularies.  
Provides configuration loading without importing shopping-agent modules.

**`backend/models.py`**  
Defines the normalized `Product` record and shared one-size value.  
Keeps catalog data types independent of intent parsing and recommendation logic.

**`backend/category_rules.py`**  
Defines deterministic tag and title/description rules for category eligibility.  
Allows catalog consumers to use category filtering without importing the agent's matching engine.

**`backend/__init__.py`**  
Marks `backend` as a Python package.  
Allows imports such as `backend.catalog` and `python -m backend.viewer`.

**`backend/catalog.py`**  
Loads the configured CSV, drops excluded/invalid rows, groups duplicate SKUs, and splits retailer tags.  
Maps each row into the common product model, adds color and size/availability data, and caches normalized products.

**`backend/legacy_catalog.py`**  
Preserves the GitHub app's no-argument `backend.catalog.load_catalog()` DataFrame interface.  
Reads the same local CALPAK CSV, filters available variants, and deduplicates parent products without changing the app.

**`backend/database_test_client.py`**  
Checks connectivity to the existing shared Neon database and prints catalog counts and a few product variants.  
Uses read-only transactions and a local `DATABASE_URL`; no AI, schema changes, or data loading is involved.

**`backend/database_config.py`**  
Loads nonempty values from `backend/.env.local` for the client and loader without overriding process settings.  
Resolves the file relative to the backend code, not the current directory; project-root environment files are not read.

**`backend/colors.py`**  
Converts Nordstrom's numeric color codes and CALPAK's named variant colors into shared color families and shades.  
This lets the agent and viewer display and filter colors consistently across retailers.

**`backend/database_loader.py`**  
Runs the same catalog enrichment used by the viewer, maps parent products and buyable variants, and bulk-loads PostgreSQL.  
It reads the Nordstrom and CALPAK CSVs using their retailer configs and reuses `backend/catalog.py`; this is project-specific code, not a copied third-party loader.  
Its database mapping follows `backend/data/database.md`, based on PRD v2 and `plan.md`; synthetic Nordstrom size/stock is flagged and CALPAK availability remains source-backed.

**`backend/catalog_search.py`**  
Read-only query functions for the agent's search nodes, following `backend/data/database.md` section 11: `search_catalog`
(filters + keyword ranking + near misses), `exact_search`, `keyword_search`, `near_miss_search`, `carry_on_fit`,
`get_products`, `catalog_facets`, `suggest_brands`. The LLM fills a `SearchRequest`; results are pydantic models.
Semantic ranking is optional (`query_vector=`) until embeddings are populated.

**`backend/agent_graph.py`** and **`backend/skills/comparison_writeup.md`**  
LangGraph search-and-compare flow: the LLM turns the shopper prompt into a `SearchRequest` (structured output),
`search_catalog` runs it, and the comparison write-up skill picks and compares 2-4 results. Picks whose IDs are not
in the search results are dropped. Model and temperature come from the retailer config (`llm`); put
`OPENAI_API_KEY` in `backend/.env` (git-ignored), never in the tracked `backend/.env.local`.
Try it: `python -m backend.agent_graph "Navy blazer under $150 in size M" --retailer nordstrom`.

**`backend/migrations/001_initial_schema.sql`**  
Creates the PostgreSQL 16 schema, pgvector/pg_trgm extensions, search indexes, and retailer-isolation constraints.  
The loader tracks migration checksums so applied migrations are not silently changed.

**`backend/viewer.py`**  
Loads the normalized catalog and serves a local, read-only API for filtering and paging through products.  
It uses Python's standard HTTP server and does not invoke agent or LLM code.

**`backend/viewer.html`**  
Provides the browser UI with search, category, brand, color, size, price, and availability filters.  
Renders matching normalized records as product cards without calling the shopping agent.

### Configuration files

**`backend/config/retailers/nordstrom.json`**  
Maps Nordstrom CSV columns and subcategory tags, selects its color lookup, and configures synthetic apparel/shoe stock.  
Also defines Nordstrom search categories, merchandising boosts, and retailer-specific guardrails.

**`backend/config/retailers/calpak.json`**  
Maps CALPAK variant columns and pipe-separated tags, uses source availability, and drops non-product rows.  
Maps luggage product types to size values such as mini carry-on, carry-on/cabin, and medium/large check-in.

**`backend/config/category_packs/apparel.json`**  
Defines apparel and shoe size vocabularies used for Nordstrom's synthetic per-size stock.  
It contains enrichment values only, not occasion or style metadata.

**`backend/config/category_packs/travel.json`**  
Defines the luggage size values used to normalize and filter CALPAK luggage, plus the one-size vocabulary.  
The retailer config maps source product types to these canonical values.

### Source data and tests

**`backend/data/nordstrom product data.csv`**  
Nordstrom's source product rows, including prices, brands, colors, categories, and subcategory tags.  
The catalog loader deduplicates these rows and generates explicitly synthetic size/stock data.

**`backend/data/calpak_catalog_variants.csv`**  
CALPAK's active variant-level source, including SKU, product type, option color, prices, tags, and availability.  
The loader uses the source availability flag; unit inventory quantities are not present in the file.

**`backend/data/calpak_catalog_full.json`**  
Full raw CALPAK catalog snapshot retained as source/reference data.  
The current loader uses the normalized variants CSV instead.

**`backend/tests/test_catalog.py`**  
Tests retailer-specific column mapping, SKU deduplication, color/size normalization, and source/synthetic stock behavior.  
Uses small in-memory rows and does not require an API key or an LLM.

**`backend/tests/test_database_loader.py`**  
Tests database-field normalization, CALPAK tag cleanup, and grounded CALPAK description parsing.  
Runs without a database connection or an LLM.

**`backend/tests/test_viewer.py`**  
Tests combined catalog filters and the local viewer's HTML, options, pagination, and invalid-filter responses.  
Uses a small in-memory catalog; no AI or LLM is started.

**`backend/tests/__init__.py`**  
Marks the backend tests directory as an importable Python package.  
This allows `unittest discover -s backend\tests -t .` to find the data-layer tests.

`backend/.cache/*.pkl` files are generated normalized-catalog caches; do not edit them. Python `__pycache__` files are
also generated and are not source inputs.

## PostgreSQL catalog setup

The versioned schema and repeatable loader use the latest design in `backend/data/database.md`. From the project
root (the folder containing `backend`), install the data-layer dependencies:

```powershell
python -m pip install -r backend\requirements.txt
```

The backend is self-contained: `configuration.py`, `models.py`, and `category_rules.py` supply validated
configuration, product records, and category eligibility rules. No shopping-agent package or LLM is required.

Configure `DATABASE_URL` and optionally `DATABASE_URL_UNPOOLED` in `backend/.env.local`; the loader prefers the
unpooled URL for bulk loading. Both the client and loader read only this backend-local file, regardless of the
working directory, with existing process environment values taking precedence. They do not read project-root
`.env` or `.env.local` files. If `neon init` creates an environment file in the project root, move the settings
into `backend/.env.local`. From the project root, preview the enriched row counts or load both retailers:

```powershell
python -m backend.database_loader --dry-run
python -m backend.database_loader
```

Normal loads are transactional and repeatable: existing product/variant IDs are retained, catalog entries removed
from the source are marked inactive or out of stock, and changed search text clears any old embedding. To rebuild the
managed tables and reload from scratch (this also removes sessions, carts, and review-cache rows), run:

```powershell
python -m backend.database_loader --reset --yes
```

The loader deterministically synthesizes only the Nordstrom size/stock already produced by `catalog.py`; it marks
those fields as synthetic. CALPAK availability stays source-backed. It does not call an LLM, invent luggage
dimensions/airline limits, generate reviews, or create embeddings; those tables/columns remain ready for later steps.

## Local Docker PostgreSQL and vector embeddings

This optional setup runs PostgreSQL 16 with pgvector and Ollama locally. It uses the same migration and catalog
loader as the shared database, but passes the local connection URL directly and never reads or changes
`backend/.env.local`. Install and start Docker Desktop before running setup. The script downloads the images,
creates an isolated Python environment, and downloads the embedding model.

From the project root, run:

```powershell
python backend\setup_local_database.py setup
```

On macOS, run `python3 backend/setup_local_database.py setup`. Setup creates the local-only `backend/.env.docker`,
starts containers bound to localhost, loads both retailer catalogs, and generates 1,024-dimensional vectors with
Ollama's `bge-large` model. The backfill commits in batches and can resume after interruption. Allow several
gigabytes for the images, model, database, and index; full-catalog CPU embedding can take many hours.

If Ollama reports `x509: certificate signed by unknown authority` on a corporate network, obtain your
organization's approved proxy CA as a PEM `.crt` file and add it to the Ollama container's trust store:

```powershell
docker compose --env-file backend/.env.docker -f backend/docker-compose.local.yml cp path-to-approved-ca.crt ollama:/usr/local/share/ca-certificates/retail-proxy.crt
docker compose --env-file backend/.env.docker -f backend/docker-compose.local.yml exec -T -u 0 ollama update-ca-certificates
docker compose --env-file backend/.env.docker -f backend/docker-compose.local.yml restart ollama
```

Rerun `setup` with TLS verification enabled. The model is cached in a Docker volume, so subsequent runs don't
contact the model registry if it is already present. If the container is recreated and a fresh model download is
needed, reapply the approved CA to the new container.

Useful follow-up commands:

```powershell
python backend\setup_local_database.py status
python backend\setup_local_database.py embed --batch-size 8
python backend\setup_local_database.py stop
```

`stop` retains the PostgreSQL data and downloaded model. `embed --reembed` replaces all active-product vectors
in the local database only. PostgreSQL defaults to port `55432` and Ollama to `11434`; both bind to `127.0.0.1`.
Removing the Compose volumes deletes the local catalog and model cache.

## Choosing the agent's catalog database

[`database_target.json`](./database_target.json) controls the database used by the agent's catalog queries.
It defaults to `{"target": "local"}`, which connects to Docker PostgreSQL at `127.0.0.1:55432`.
Run the local Docker setup and use its generated `.env.docker` next to this README. If Docker was set up from a
different checkout on the same machine, copy only that generated file into this checkout's `backend` folder.
The file is git-ignored; it supplies `POSTGRES_PASSWORD` and an optional `POSTGRES_PORT`.

To use the shared database, set the target to `neon` and configure `DATABASE_URL` in the environment or
in `backend/.env.local`. A local connection failure does not fall back to Neon. This switch applies to the agent
and catalog search, not the database loader or the shared-database test client. It does not change the LLM
provider or enable vector ranking.

## Testing the shared Neon database

Ask the database owner for the connection URL through a secure channel. Put `DATABASE_URL` in
`backend/.env.local` or set it in the process environment. The committed backend-local template includes both
database URL keys with empty values plus the Neon branch metadata. Never commit a real connection URL.
This template is tracked: `.gitignore` does not protect subsequent edits to an already tracked file.
Before committing, confirm both URL values remain blank in the staged version.
The client uses the existing database directly; do not run the loader just to test connectivity.

```powershell
python -m backend.database_test_client --retailer calpak --limit 5
python -m backend.database_test_client --retailer nordstrom --limit 5
```

The client prints database-wide catalog counts followed by up to 50 variants for the requested retailer.
It prefers an existing process-level `DATABASE_URL`, then `backend/.env.local`. Use a read-only database
role when sharing access; a retailer query filter is not a database permission boundary.

## Data-layer tests and viewer

```powershell
python -m unittest discover -s backend\tests -t .
$env:RUN_DB_TESTS = "1"; python -m unittest backend.tests.test_catalog_search   # read-only queries against selected DB
$env:RUN_LLM_TESTS = "1"; python -m unittest backend.tests.test_agent_graph -v   # real prompts via OpenAI + selected DB
python -m backend.viewer --help
python -m backend.viewer
```

The viewer reads and enriches the local CSVs, not Neon. Both source CSVs and the CALPAK JSON snapshot are included.
Generated caches are excluded from version control; the committed environment template contains no credentials.
