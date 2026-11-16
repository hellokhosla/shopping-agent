# Team 12 — Retail Shopping Agent

Maven "Building Agentic AI Applications" capstone. V0 (Workflow) build of the "Middle" layer — model selection, guardrails, intent routing (Kapil + Kavya) — wired to the real Calpak catalog.

## Architecture (V0 — Workflow)

Code is the center of control. The model is called once per message, only to classify intent and extract constraints:

```
user message -> classify() [the only model call] -> dispatch table -> catalog search (code) -> formatted answer (code)
```

- `middle/classify.py` — `ShoppingIntent` schema + the one structured-output call per message.
- `middle/guardrails.py` — hard limits (price ceiling, result count) enforced in code, independent of what the model extracted.
- `middle/dispatch.py` — one plain function per objective (`cross_category`, `single_category`, `specific_product`, `branded`), all reading the same catalog DataFrame.
- `catalog.py` — loads the real Calpak product catalog via pandas.
- `app.py` — Gradio chat UI wiring it all together.

V1 (Agentic) will flip this: the model becomes the center of control, calling tools (catalog search, maybe order history) in a loop until it's satisfied, instead of one classify-then-dispatch pass.

## Running it

```bash
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
pip install -r requirements.txt
python app.py
```

## Data

`data/calpak_catalog_variants.csv` — real Calpak Shopify product/variant export (178 in-stock products after filtering). Nordstrom dataset (shared separately in Slack, ~48MB) isn't included here yet — add it as a second catalog source if the demo needs multi-retailer support.
