# Team 12 — Retail Shopping Agent

Maven "Building Agentic AI Applications" capstone. V0 (Workflow) build, wired to the real Calpak catalog.

## Code ownership

Three independent folders, matching the team's own role split — see [`OWNERS.md`](OWNERS.md) for the full breakdown and why it's structured this way. Only `app.py` imports across folders.

| Folder | Owners | Area |
|---|---|---|
| `middle/` | Kapil, Kavya | Model selection, guardrails, intent routing |
| `backend/` | Gaurav, Prasad | Catalog ingestion / data |
| `frontend/` | Jasmeet, Carly | UI, theming, result display |
| `evals/` | Everyone | Component-level evals (not started yet) |

## Architecture (V0 — Workflow)

Code is the center of control. The model is called once per message, only to classify intent and extract constraints:

```
user message -> middle.classify() [the only model call] -> middle.DISPATCH -> backend.load_catalog() (code) -> frontend.format_rows() (code)
```

V1 (Agentic) will flip this: the model becomes the center of control, calling tools (catalog search, maybe order history) in a loop until it's satisfied, instead of one classify-then-dispatch pass.

## Running it

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
pip install -r requirements.txt
python app.py
```

## Data

The existing app keeps its CALPAK DataFrame interface through `backend.catalog.load_catalog()`.
The complete data-layer backend, both retailer CSVs, CALPAK JSON snapshot, repeatable PostgreSQL loader,
schema, viewer, and tests are included under `backend/`. See [backend setup and enrichment](backend/README.md).
The shared configuration, product models, and category-rule dependencies are included under `retail_agent/`;
no additional agent implementation or model calls are needed by the backend.

## Checking Neon database connectivity

`backend/neon_client.py` is a read-only sample client. It checks the connection, prints database row counts, and
queries a few product variants without changing data:

```bash
cp .env.example .env
# Set DATABASE_URL in .env to the shared Neon PostgreSQL connection string.
pip install -r requirements.txt
python -m backend.neon_client --retailer calpak --limit 5
```

Use the connection string from the Neon Console and keep it in your local `.env` or `.env.local` file.
Never commit or paste the real URL into source code, `.env.example`, or chat; both local environment files
are ignored by Git. The client uses read-only transactions; it does not reload or change the shared database.
