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
        image = row.get("image_url")
        thumbnail = f"![{row['title']}]({image})\n" if isinstance(image, str) and image else ""
        lines.append(f"{thumbnail}**[{row['title']}]({row['product_url']})** — {price}")
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


CALPAK_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.red,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Poppins"), "sans-serif"],
).set(
    body_background_fill="#FAF3E7",
    body_background_fill_dark="#FAF3E7",
    button_primary_background_fill="#6B1A2B",
    button_primary_background_fill_hover="#8A2238",
    button_primary_text_color="#FAF3E7",
)

CALPAK_CSS = """
.gradio-container { max-width: 900px !important; margin: auto; }
#nav-row { align-items: center; border-bottom: 2px solid #6B1A2B; padding-bottom: 10px; margin-bottom: 10px; }
#nav-left { display: flex; align-items: center; gap: 26px; height: 100%; }
#wordmark { letter-spacing: 0.15em; font-weight: 700; font-size: 24px; color: #6B1A2B; white-space: nowrap; }
#nav-links { display: flex; gap: 16px; font-size: 13px; color: #3a2a1e; white-space: nowrap; }
#nav-links span { cursor: default; }
#search-box { min-width: 160px; }
#search-box textarea, #search-box input {
    border-radius: 999px !important; border: 1px solid #6B1A2B !important;
    padding: 6px 16px !important; font-size: 13px !important;
}
"""

NAV_LEFT_HTML = """
<div id="nav-left">
  <div id="wordmark">CALPAK</div>
  <div id="nav-links">
    <span>Shop All</span><span>Best Sellers</span><span>Bags</span>
    <span>Luggage</span><span>Organizers &amp; More</span><span>Gifts</span>
  </div>
</div>
"""


def on_search(message, history):
    history = history or []
    if not message or not message.strip():
        return history, ""
    answer = respond(message, history)
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": answer},
    ]
    return history, ""


with gr.Blocks(title="CALPAK — Shopping Assistant") as demo:
    with gr.Row(elem_id="nav-row"):
        gr.HTML(NAV_LEFT_HTML, elem_id="nav-left-wrap")
        search_box = gr.Textbox(
            elem_id="search-box",
            placeholder="Search",
            show_label=False,
            container=False,
            scale=1,
        )

    gr.Markdown(
        "Team 12 Retail Shopping Agent — Middle layer (model selection, guardrails, "
        "intent routing), V0 Workflow. The model classifies intent once per message; "
        "code does everything else — search, price limits, formatting.",
    )

    chatbot = gr.Chatbot(
        label=None,
        show_label=False,
        height=320,
        placeholder="Try *\"best carry-on under $150\"* or *\"a gift for my dad\"* in the search box above.",
    )

    gr.Examples(
        examples=[
            "Find a gift for my dad, something travel related",
            "Best carry-on bag under $150",
            "Do you have the Trek Duffel 26L",
            "Show me your newest bags under $100",
        ],
        inputs=search_box,
    )

    search_box.submit(on_search, inputs=[search_box, chatbot], outputs=[chatbot, search_box])

if __name__ == "__main__":
    demo.launch(theme=CALPAK_THEME, css=CALPAK_CSS)
