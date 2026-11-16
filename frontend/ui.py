"""OWNER: Jasmeet, Carly — Frontend (customer engagement / UI).

Everything about how results are *displayed* lives here: the markdown/image
formatting of catalog rows, and the gr.Blocks page layout. Takes a
search_handler callback from app.py instead of importing Middle/Backend
directly, so this file never has to know how a query actually gets answered.
"""

from __future__ import annotations

import gradio as gr

from .theme import CALPAK_CSS, CALPAK_THEME, NAV_LEFT_HTML

EXAMPLES = [
    "Find a gift for my dad, something travel related",
    "Best carry-on bag under $150",
    "Do you have the Trek Duffel 26L",
    "Show me your newest bags under $100",
]


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


def build_demo(search_handler) -> gr.Blocks:
    """search_handler(message: str) -> str, the combined Middle+Backend answer."""

    def on_search(message, history):
        history = history or []
        if not message or not message.strip():
            return history, ""
        answer = search_handler(message)
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
            elem_id="results",
            label=None,
            show_label=False,
            height="auto",
            resizable=False,
            placeholder="Try *\"best carry-on under $150\"* or *\"a gift for my dad\"* in the search box above.",
        )

        gr.Examples(examples=EXAMPLES, inputs=search_box)

        search_box.submit(on_search, inputs=[search_box, chatbot], outputs=[chatbot, search_box])

    return demo


THEME = CALPAK_THEME
CSS = CALPAK_CSS
