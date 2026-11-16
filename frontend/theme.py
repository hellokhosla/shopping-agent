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
#results, #results .bubble-wrap, #results > div {
    overflow-y: visible !important; max-height: none !important;
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
