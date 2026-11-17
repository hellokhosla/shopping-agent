# Backend files and data enrichment

The retailer JSON config maps each retailer's source columns to common fields; the category pack supplies size
vocabularies. `catalog.py` uses these settings to clean and normalize source rows into shared `Product` records,
enrich colors, apply source or synthetic availability, and cache the result. Agent logic is not involved in this
pipeline.

### Core files

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

**`backend/colors.py`**  
Converts Nordstrom's numeric color codes and CALPAK's named variant colors into shared color families and shades.  
This lets the agent and viewer display and filter colors consistently across retailers.

**`backend/database_loader.py`**  
Runs the same catalog enrichment used by the viewer, maps parent products and buyable variants, and bulk-loads PostgreSQL.  
It reads the Nordstrom and CALPAK CSVs using their retailer configs and reuses `backend/catalog.py`; this is project-specific code, not a copied third-party loader.  
Its database mapping follows `backend/data/database.md`, based on PRD v2 and `plan.md`; synthetic Nordstrom size/stock is flagged and CALPAK availability remains source-backed.

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

The backend also requires the shared `retail_agent/__init__.py`, `config.py`, `models.py`, and `matching_engine.py`
modules included in the repository. These supply validated configuration, product types, and category rules;
they do not call an LLM. No other shopping-agent modules are required by the backend.

`neon init` creates a local `.env.local` with `DATABASE_URL` and `DATABASE_URL_UNPOOLED`; the loader prefers the
unpooled URL for bulk loading. A workspace `.env` or process-level `DATABASE_URL` is also supported. These local
environment files are ignored by `.gitignore`; never paste connection URLs into source code or chat. From the
project root, preview the enriched row counts or load both retailers:

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

## Testing the shared Neon database

Ask the database owner for the connection URL through a secure channel. Put `DATABASE_URL` in the project-root
`.env` or `.env.local` file, using `backend/.env.example` as a template. Never commit a real connection URL.
The client uses the existing database directly; do not run the loader just to test connectivity.

```powershell
python -m backend.database_test_client --retailer calpak --limit 5
python -m backend.database_test_client --retailer nordstrom --limit 5
```

The client prints database-wide catalog counts followed by up to 50 variants for the requested retailer.
It prefers an existing process-level `DATABASE_URL`, then `.env.local`, then `.env`. Use a read-only database
role when sharing access; a retailer query filter is not a database permission boundary.

## Data-layer tests and viewer

```powershell
python -m unittest discover -s backend\tests -t .
python -m backend.viewer --help
python -m backend.viewer
```

The viewer reads and enriches the local CSVs, not Neon. Both source CSVs and the CALPAK JSON snapshot are included.
Generated caches and local credentials are excluded from version control.
