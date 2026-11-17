"""OWNER: Jasmeet, Carly — Frontend (customer engagement / UI).

Everything about how results are *displayed* lives here: the product-card
formatting of catalog rows, and the gr.Blocks page layout. Takes a
search_handler callback from app.py instead of importing Middle/Backend
directly, so this file never has to know how a query actually gets answered.

Layout: the page is a stand-in storefront; the assistant is a floating panel
pinned bottom-left (see the "popup chat" block in theme.py), opened by the
launcher button or by submitting the nav search box.
"""

from __future__ import annotations

import html
import re

import gradio as gr

from .theme import CALPAK_CSS, CALPAK_THEME, NAV_LEFT_HTML

EXAMPLES = [
    "Find a gift for my dad, something travel related",
    "Best carry-on bag under $150",
    "Do you have the Luka Duffel",
    "Show me your newest bags under $100",
]

NO_RESULTS = "I couldn't find anything matching that — want to loosen the price or category?"

# The design is light-only. When the visitor's system is in dark mode, Gradio
# adds a "dark" class to <body> and recolors its own components (chat area,
# text boxes, buttons) while our custom CSS stays light, which makes text
# unreadable. Remove the class on load and keep it removed.
FORCE_LIGHT_MODE_JS = """
() => {
  const strip = () => document.body.classList.remove('dark');
  strip();
  new MutationObserver(strip).observe(document.body, { attributes: true, attributeFilter: ['class'] });
}
"""

# After an answer lands, put the shopper's latest question at the top of the
# message area, so a tall grid of cards is read from its first row, not its last.
SCROLL_TO_LATEST_QUESTION_JS = """
() => {
  setTimeout(() => {
    const rows = document.querySelectorAll('#chat-messages .user-row');
    const scroller = document.querySelector('#chat-messages .bubble-wrap');
    if (!rows.length || !scroller) return;
    const last = rows[rows.length - 1];
    scroller.scrollTop += last.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 8;
  }, 150);
}
"""

_BEST_FOR = re.compile(r"Best for\s*:\s*(.+?)(?:\s+Features\s*:|$)", re.IGNORECASE | re.DOTALL)


def _best_for(description) -> str:
    """Pull the catalog's own 'Best for: ...' sentence out of the description text."""
    if not isinstance(description, str):
        return ""
    match = _BEST_FOR.search(description)
    return match.group(1).strip().rstrip(".") if match else ""


def _thumbnail(image_url) -> str:
    """Ask the image CDN for a card-sized image instead of the full-size original."""
    if not isinstance(image_url, str) or not image_url:
        return ""
    return image_url + ("&" if "?" in image_url else "?") + "width=480"


def _card(row) -> str:
    title = html.escape(str(row["title"]))
    url = html.escape(str(row["product_url"]), quote=True)
    price = f"${row['price']:.2f}"
    compare = row.get("compare_at_price")
    was = f'<span class="pc-was">${compare:.2f}</span>' if compare and compare > row["price"] else ""
    image = _thumbnail(row.get("image_url"))
    photo = (
        f'<a class="pc-photo" href="{url}" target="_blank" rel="noopener">'
        f'<img src="{html.escape(image, quote=True)}" alt="{title}" loading="lazy"></a>'
        if image
        else ""
    )
    best_for = _best_for(row.get("description_text"))
    why = (
        f'<div class="pc-why"><span class="pc-why-label">Best for</span> {html.escape(best_for)}</div>'
        if best_for
        else ""
    )
    return (
        '<div class="pc-card">'
        f"{_badge(row)}"
        f"{photo}"
        '<div class="pc-body">'
        f'<a class="pc-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
        f'<div class="pc-price"><span class="pc-now">{price}</span>{was}</div>'
        f"{why}"
        f"{_tradeoff(row)}"
        '<div class="pc-actions">'
        f'<a class="pc-link" href="{url}" target="_blank" rel="noopener">View product</a>'
        # Add to cart is display-only for now: no click handler and no cart state.
        '<button type="button" class="pc-cart">Add to cart</button>'
        "</div>"
        "</div></div>"
    )


# --------------------------------------------------------------------------
# PLACEHOLDERS — TO BE LINKED TO MIDDLE (Kapil, Kavya) WHEN READY
#
# Badges, trade-offs and the near-miss strip need judgments the frontend can't
# make from a catalog row. Until middle/ supplies them, the UI shows clearly
# marked placeholder text so the layout can be reviewed.
#
# The contract this file already honors, so middle/ can plug in without any
# frontend change:
#   - badge:     optional "badge" column on the rows, e.g. "Best match"
#   - trade-off: optional "tradeoff" column on the rows, e.g. "$24 more than the Hue"
#   - near miss: optional near_miss argument to format_rows(), a dict with
#                "title", "product_url" and "reason" (what it gives up)
#
# Set SHOW_PLACEHOLDERS = False to hide all three until real values arrive.
# --------------------------------------------------------------------------
SHOW_PLACEHOLDERS = True

PLACEHOLDER_BADGE = "Badge placeholder"
PLACEHOLDER_TRADEOFF = "placeholder, to come from the middle layer."
PLACEHOLDER_NEAR_MISS = (
    "Placeholder. A product that almost fits, and what it gives up, will appear here "
    "once the middle layer supplies it."
)


def _text(value) -> str:
    """A cell value as display text; missing values (None, NaN, '') become ''."""
    if value is None or value != value:  # NaN is the only value not equal to itself
        return ""
    return str(value).strip()


def _badge(row) -> str:
    # TODO(middle): replace the placeholder by adding a "badge" column to the rows.
    badge = _text(row.get("badge"))
    if badge:
        return f'<span class="pc-badge">{html.escape(badge)}</span>'
    if SHOW_PLACEHOLDERS:
        return f'<span class="pc-badge pc-placeholder">{PLACEHOLDER_BADGE}</span>'
    return ""


def _tradeoff(row) -> str:
    # TODO(middle): replace the placeholder by adding a "tradeoff" column to the rows.
    tradeoff = _text(row.get("tradeoff"))
    if tradeoff:
        return f'<div class="pc-tradeoff"><span class="pc-why-label">Trade-off:</span> {html.escape(tradeoff)}</div>'
    if SHOW_PLACEHOLDERS:
        return (
            '<div class="pc-tradeoff pc-placeholder">'
            f'<span class="pc-why-label">Trade-off:</span> {PLACEHOLDER_TRADEOFF}</div>'
        )
    return ""


def _near_miss(near_miss) -> str:
    # TODO(middle): replace the placeholder by passing near_miss= to format_rows().
    if near_miss:
        title = html.escape(_text(near_miss.get("title")))
        url = html.escape(_text(near_miss.get("product_url")), quote=True)
        reason = html.escape(_text(near_miss.get("reason")))
        name = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
        return f'<div class="pc-nearmiss"><span class="pc-nearmiss-tag">Near miss</span><span>{name} {reason}</span></div>'
    if SHOW_PLACEHOLDERS:
        return (
            '<div class="pc-nearmiss pc-placeholder">'
            f'<span class="pc-nearmiss-tag">Near miss</span><span>{PLACEHOLDER_NEAR_MISS}</span></div>'
        )
    return ""


def format_rows(rows, near_miss=None) -> str:
    """Catalog rows -> a grid of product cards (one HTML block, no blank lines).

    near_miss is optional and not passed by app.py yet; see the PLACEHOLDERS note above.
    """
    if rows is None or len(rows) == 0:
        return NO_RESULTS
    cards = "".join(_card(row) for _, row in rows.iterrows())
    return f'<div class="pc-results"><div class="pc-grid">{cards}</div>{_near_miss(near_miss)}</div>'


def build_demo(search_handler) -> gr.Blocks:
    """search_handler(message: str) -> str, the combined Middle+Backend answer."""

    def on_search(message, history):
        history = history or []
        if not message or not message.strip():
            return history, "", gr.update(), gr.update()
        answer = search_handler(message)
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        return history, "", gr.update(visible=True), gr.update(visible=False)

    def open_panel():
        return gr.update(visible=True), gr.update(visible=False)

    def close_panel():
        return gr.update(visible=False), gr.update(visible=True)

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

        launcher = gr.Button("Ask the shopping assistant", elem_id="chat-launcher", variant="primary")

        with gr.Column(elem_id="chat-panel", visible=False) as panel:
            with gr.Row(elem_id="chat-header"):
                gr.HTML('<div id="chat-title">Shopping assistant</div>')
                close = gr.Button("Close", elem_id="chat-close", size="sm", scale=0, min_width=88)

            chatbot = gr.Chatbot(
                elem_id="chat-messages",
                label=None,
                show_label=False,
                resizable=False,
                autoscroll=False,
                buttons=[],
                placeholder="Describe the trip, the person or the budget, or pick an example below.",
            )

            reply_box = gr.Textbox(
                elem_id="chat-input",
                placeholder="Describe what you need",
                show_label=False,
                container=False,
                submit_btn=True,
            )
            gr.Examples(examples=EXAMPLES, inputs=reply_box, label="Try an example", elem_id="chat-examples")
            gr.HTML('<div id="chat-footnote">Course project demo. Not affiliated with CALPAK.</div>')

        demo.load(None, None, None, js=FORCE_LIGHT_MODE_JS)
        launcher.click(open_panel, outputs=[panel, launcher])
        close.click(close_panel, outputs=[panel, launcher])
        for box in (search_box, reply_box):
            box.submit(
                on_search, inputs=[box, chatbot], outputs=[chatbot, box, panel, launcher]
            ).then(None, None, None, js=SCROLL_TO_LATEST_QUESTION_JS)

    return demo


THEME = CALPAK_THEME
CSS = CALPAK_CSS
