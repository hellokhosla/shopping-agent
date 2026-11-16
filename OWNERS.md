# Code ownership

Matches the role split from the team scratchpad (2026-11-15/16). Each folder
is a separate area to innovate in — none of them import each other directly,
only `app.py` wires them together, so you can rework your folder without
breaking someone else's.

| Area | Owners | Folder | What lives there |
|---|---|---|---|
| **Middle** — model selection, guardrails, intent routing | Kapil, Kavya | `middle/` | `classify.py` (the one model call per message), `guardrails.py` (hard limits), `dispatch.py` (classification -> result-shaping functions) |
| **Backend** — catalog ingestion, data curation/metadata | Gaurav, Prasad | `backend/` | `catalog.py` (loads the product catalog). Swap in MCP/API/data-warehouse loading here, or add a second retailer, without anything else needing to change |
| **Frontend** — customer engagement / UI | Jasmeet, Carly | `frontend/` | `theme.py` (brand colors/CSS/nav markup), `ui.py` (page layout, result formatting/images) |
| **Evals** — component-level evaluation | Everyone, after system design lands | `evals/` | empty for now — add retrieval/classification/answer-quality evals here |
| **System design / integration** | Everyone | `app.py` | wires the three areas together; the only file allowed to import across folders |

## Why it's split this way

This mirrors the model-vs-code architecture itself: `middle/` is genuinely the
only place a model gets called in V0. `backend/` and `frontend/` are both
plain code with no model involvement — one fetches data, the other displays
it. Keeping them in separate folders with one-directional imports (only
`app.py` reaches into all three) means each pair can iterate on their area
without needing to understand or break the others' code.
