"""V0 (Workflow): classify -> dispatch -> search -> format.

Code is the center of control. The model is called exactly once per message,
only to classify intent and extract constraints; every step after that is
plain Python running the same way every time.
"""

from __future__ import annotations

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from catalog import load_catalog
from middle.classify import classify
from middle.dispatch import DISPATCH
from middle.guardrails import clamp_price


def format_rows(rows) -> str:
    if rows is None or len(rows) == 0:
        return "I couldn't find anything matching that — want to loosen the price or category?"
    lines = []
    for _, row in rows.iterrows():
        price = f"${row['price']:.2f}"
        compare = row.get("compare_at_price")
        if compare and compare > row["price"]:
            price += f" ~~${compare:.2f}~~"
        lines.append(f"**[{row['title']}]({row['product_url']})** — {price}")
    return "\n\n".join(lines)


def respond(message: str, history) -> str:
    intent = classify(message)
    intent.max_price = clamp_price(intent.max_price)

    catalog = load_catalog()
    handler = DISPATCH[intent.objective]
    rows = handler(catalog, intent)

    answer = format_rows(rows)
    debug = f"\n\n<sub>_intent: {intent.objective} · category={intent.category} · brand={intent.brand} · max_price={intent.max_price}_</sub>"
    return answer + debug


demo = gr.ChatInterface(
    respond,
    title="Calpak Shopping Assistant — V0 (Workflow)",
    description=(
        "Team 12 Retail Shopping Agent. This is the Middle layer (model selection, "
        "guardrails, intent routing) wired to the real Calpak catalog. "
        "The model classifies intent once per message; code does everything else."
    ),
    examples=[
        "Find a gift for my dad, something travel related",
        "Best carry-on bag under $150",
        "Do you have the Trek Duffel 26L",
        "Show me your newest bags under $100",
    ],
)

if __name__ == "__main__":
    demo.launch()
