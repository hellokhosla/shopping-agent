"""Connect the CALPAK storefront to the backend search-and-compare workflow."""

from __future__ import annotations

import html

import pandas as pd

from backend.agent_graph import run
from frontend.theme import CALPAK_CSS, CALPAK_THEME
from frontend.ui import build_demo, format_rows


def respond(message: str) -> str:
    state = run(message, retailer_id="calpak")
    result = state["result"]
    comparison = state["comparison"]
    summary = f'<div class="pc-summary">{html.escape(comparison.summary)}</div>'
    hits = {hit.product_id: hit for hit in [*result.hits, *result.near_misses]}
    rows = []
    for pick in comparison.picks:
        hit = hits.get(pick.product_id)
        if hit is None or not hit.variants:
            continue
        variant = hit.variants[0]
        tradeoff = pick.trade_off
        if hit.is_near_miss:
            tradeoff = "; ".join([*hit.miss_reasons, tradeoff])
        rows.append({
            "title": hit.title,
            "product_url": hit.product_url,
            "image_url": variant.image_url or hit.image_url,
            "price": variant.price,
            "compare_at_price": variant.was_price,
            "why": pick.why,
            "tradeoff": tradeoff,
            "badge": "Near miss" if hit.is_near_miss else "",
        })
    if not rows:
        if result.hits or result.near_misses:
            return summary + '<div class="pc-empty">No verified product picks were returned.</div>'
        return summary
    return summary + format_rows(pd.DataFrame(rows))


demo = build_demo(respond)

if __name__ == "__main__":
    demo.launch(theme=CALPAK_THEME, css=CALPAK_CSS)
