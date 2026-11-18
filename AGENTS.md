# AGENTS.md

Guide for any AI coding agent working in this repo. Read this first, then the files it points to.

## What this project is

Team 12's retail shopping agent (Maven "Building Agentic AI Applications" capstone): a shopper asks in plain
language and gets products from a retailer's real catalog. Two demo retailers: **Nordstrom** (apparel/shoes) and
**CALPAK** (luggage/travel).

## Where to look

| You need… | Look at |
|---|---|
| Product requirements, scope, demo scenarios | `ShoppingAgent-PRD.md` (root) |
| Target architecture and decisions (V1) | `plan.md` (root) — sections 5–13 cover the graph, search, guardrails, config, pipeline, API, models, open questions |
| Database design (tables, columns, search queries) | `backend/data/database.md` — **the latest version**; the root `database.md` is an old copy, ignore it |
| Source data | `backend/data/` — `nordstrom product data.csv`, `calpak_catalog_variants.csv`, `calpak_catalog_full.json`. The root `data/` folder holds older copies; don't use them |
| Who owns which folder | `OWNERS.md` |
| How the backend/data layer works, how to load and test the DB | `backend/README.md` |
| Running the current app | `README.md` |

## Folder map

- `app.py` — wires everything together. **The only file allowed to import across folders.**
- `middle/` — model calls, guardrails, intent routing (Kapil, Kavya).
- `backend/` — catalog ingestion, normalization, Postgres schema and loader (Gaurav, Prasad).
  - `config/retailers/*.json` — per-retailer column mapping, tags, guardrails. `config/category_packs/*.json` — size vocabularies.
  - `migrations/` — versioned SQL schema. `database_loader.py` — loads both CSVs into Postgres.
- `frontend/` — UI and theming (Jasmeet, Carly).
- `evals/` — component evals (empty so far).

## Decisions already made

- **Target is V1 from `plan.md`**: FastAPI + a fixed LangGraph workflow + Postgres/pgvector + per-retailer config.
  The current Gradio app (`app.py`, `middle/`, `frontend/`) is V0 and legacy — don't build new features on it
  unless asked.
- **Database: shared hosted Neon Postgres** with pgvector and pg_trgm (not local Docker). Schema in
  `backend/migrations/001_initial_schema.sql`. Both retailers are loaded (122,010 products, 679,314 variants as
  of 2026-11-17).
- **Retailer configs are JSON** (`plan.md` says YAML; JSON is what was built). Adding a retailer should mean
  adding a config, not changing code.
- Nordstrom size/stock data is **synthetic** and flagged as such; CALPAK availability comes from the source.

## Still open — ask, don't assume

- Model tiers per step, the embedding model (schema assumes `vector(1024)`, i.e. Voyage), and the tracing tool
  (LangSmith vs. Arize). Embeddings are not generated yet.
- See `plan.md` §13 and the PRD "Risks and open questions" for the rest.

## Rules

- Keep the import rule: folders don't import each other; only `app.py` crosses folders.
- You may edit any folder, but call out changes outside the area the requester owns (see `OWNERS.md`).
- **Never commit secrets.** `backend/.env.local` is a tracked template — the `DATABASE_URL` values must be blank
  in anything staged. Check `git diff --cached backend/.env.local` before committing.
- Don't run `python -m backend.database_loader --reset --yes` against the shared database without explicit
  approval — it wipes and reloads shared tables. Use `--dry-run` or `backend.database_test_client` (read-only)
  to inspect.
- Use forward-slash relative paths in configs so code runs on Windows, macOS and Linux.
- Don't edit generated files (`backend/.cache/*.pkl`, `__pycache__`).

## Commands (from repo root)

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r backend/requirements.txt
.venv/bin/python -m unittest discover -s backend/tests -t .      # backend tests, no DB or LLM needed
.venv/bin/python -m backend.database_loader --dry-run            # preview load counts
.venv/bin/python -m backend.database_test_client --retailer calpak --limit 5   # read-only DB check
.venv/bin/python -m backend.viewer                               # local catalog browser (reads CSVs)
```
