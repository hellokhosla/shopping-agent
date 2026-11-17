"""OWNER: Jasmeet, Carly — Frontend (customer engagement / UI).

Calpak brand theme, CSS, and the static nav bar markup. This is the seam to
restyle freely without touching Middle or Backend code.
"""

from __future__ import annotations

import gradio as gr

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

/* ---- Popup chat: launcher button + floating panel, pinned bottom-left ---- */
#chat-launcher {
    position: fixed; left: 24px; bottom: 24px; z-index: 900;
    width: auto; min-width: 0; max-width: calc(100vw - 48px);
    border-radius: 999px; padding: 14px 22px; font-weight: 600;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.22);
}
#chat-panel {
    position: fixed; left: 24px; bottom: 24px; z-index: 1000;
    width: min(862px, calc(100vw - 48px));
    height: min(860px, calc(100vh - 48px));
    background: #FFFFFF; border-radius: 28px; padding: 18px 20px 12px 20px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.24);
    display: flex; flex-direction: column; flex-wrap: nowrap; gap: 10px; overflow: hidden;
}
/* Gradio hides a component by adding .hide; the display:flex above would otherwise win. */
#chat-panel.hide { display: none !important; }
#chat-header { align-items: center; justify-content: space-between; flex: 0 0 auto; flex-wrap: nowrap; border-bottom: 1px solid #ECE9E2; padding-bottom: 10px; }
#chat-header > *:first-child { flex: 1 1 auto; min-width: 0; }
#chat-title { font-weight: 700; font-size: 18px; color: #1A1A1A; }
#chat-close { flex: 0 0 auto !important; width: auto !important; max-width: 96px; border-radius: 999px; }
#chat-messages { flex: 1 1 0 !important; min-height: 0 !important; height: auto !important; border: 0 !important; }
#chat-messages .bubble-wrap { height: 100%; }
#chat-messages .message.bot, #chat-messages .bot .message-content { max-width: 100% !important; width: 100%; }
#chat-input, #chat-examples, #chat-footnote { flex: 0 0 auto; }
#chat-input textarea, #chat-input input {
    border-radius: 999px !important; border: 1px solid #6B1A2B !important;
    padding: 12px 18px !important; font-size: 15px !important;
}
#chat-footnote { font-size: 12px; color: #5E5A52; text-align: center; }

/* ---- Product cards inside an assistant message ---- */
.pc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; width: 100%; }
.pc-card { border: 1px solid #E0DDD6; border-radius: 16px; overflow: hidden; background: #FFFFFF; display: flex; flex-direction: column; }
.pc-photo { display: block; background: #F6F5F2; height: 200px; }
.pc-photo img { width: 100%; height: 100%; object-fit: contain; display: block; margin: 0; border-radius: 0; }
.pc-body { padding: 12px 14px 14px 14px; display: flex; flex-direction: column; gap: 8px; flex: 1 1 auto; }
.pc-title { font-weight: 600; font-size: 15px; line-height: 1.3; color: #1A1A1A !important; text-decoration: none; }
.pc-title:hover { text-decoration: underline; }
.pc-price { display: flex; align-items: baseline; gap: 8px; }
.pc-now { font-weight: 600; font-size: 16px; color: #1A1A1A; }
.pc-was { font-size: 13px; color: #5E5A52; text-decoration: line-through; }
.pc-why { font-size: 13px; line-height: 1.4; color: #3a2a1e; }
.pc-why-label { font-weight: 600; color: #1A1A1A; }
.pc-tradeoff { font-size: 13px; line-height: 1.4; color: #3a2a1e; }
.pc-actions { margin-top: auto; display: flex; flex-wrap: wrap; gap: 8px; }
.pc-link, .pc-cart {
    flex: 1 1 0; min-height: 40px; padding: 0 12px; white-space: nowrap;
    display: inline-flex; align-items: center; justify-content: center;
    border: 1px solid #6B1A2B; border-radius: 999px;
    font-family: inherit; font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer;
}
.pc-link { background: #FFFFFF; color: #6B1A2B !important; }
.pc-link:hover { background: #F6EDEF; }
.pc-cart { background: #6B1A2B; color: #FAF3E7; }
.pc-cart:hover { background: #8A2238; }

/* Badge sits over the top-left corner of the photo. */
.pc-card { position: relative; }
.pc-badge {
    position: absolute; left: 10px; top: 10px; z-index: 1;
    padding: 4px 10px; border-radius: 999px; background: #F2E76B; color: #1A1A1A;
    font-size: 12px; font-weight: 600; line-height: 1.3;
}

/* "Matched on" tags above the grid, and the no-results line. */
.pc-matched { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pc-matched-label { font-size: 13px; color: #4A4740; }
.pc-chip {
    display: inline-flex; align-items: center; min-height: 28px; padding: 0 12px;
    border-radius: 999px; background: #F3F1EC; color: #1A1A1A; font-size: 13px; font-weight: 500;
}
.pc-empty { font-size: 15px; line-height: 1.5; color: #1A1A1A; }

/* Near-miss strip under the grid. */
.pc-results, .pc-answer { display: flex; flex-direction: column; gap: 14px; width: 100%; }
.pc-nearmiss {
    display: flex; align-items: center; gap: 12px; padding: 10px 14px;
    border: 1px dashed #8A8578; border-radius: 14px; font-size: 13px; line-height: 1.45; color: #1A1A1A;
}
.pc-nearmiss-tag {
    flex: 0 0 auto; padding: 4px 10px; border-radius: 999px;
    background: #FFF1C9; border: 1px solid #8A6A00; color: #5C4A00; font-size: 12px; font-weight: 600;
}

/* Anything still waiting on the middle layer: dashed outline, muted, italic. */
.pc-placeholder { font-style: italic; color: #5E5A52; }
.pc-badge.pc-placeholder { background: #FFFFFF; border: 1px dashed #8A8578; color: #5E5A52; }
.pc-tradeoff.pc-placeholder { border: 1px dashed #C9C5BB; border-radius: 8px; padding: 6px 8px; }
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
