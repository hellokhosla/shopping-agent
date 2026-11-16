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

`data/calpak_catalog_variants.csv` — real Calpak Shopify product/variant export (178 in-stock products after filtering). Nordstrom dataset (shared separately in Slack, ~48MB) isn't included here yet — add it as a second catalog source if the demo needs multi-retailer support.
