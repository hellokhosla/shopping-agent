"""OWNER: Kapil, Kavya — Middle (model selection, guardrails, intent routing).

Hard limits enforced in code, never only in the prompt. The model's extracted
fields (max_price, etc.) are suggestions from language, not trusted bounds —
code clamps them before they ever touch a catalog query.
"""

MAX_RESULTS = 6
MAX_PRICE_CEILING = 5000.0


def clamp_price(max_price: float | None) -> float | None:
    if max_price is None:
        return None
    return min(max(max_price, 0.0), MAX_PRICE_CEILING)


def clamp_results(rows):
    return rows.head(MAX_RESULTS)
