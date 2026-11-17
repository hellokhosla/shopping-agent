"""OWNER: Jasmeet, Carly — Frontend (customer engagement / UI).

Calpak-style theme and CSS for the demo storefront and the chat panel. This is the seam to
restyle freely without touching Middle or Backend code. The storefront
markup itself lives in storefront.py.
"""

from __future__ import annotations

import gradio as gr

CALPAK_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.red,
    neutral_hue=gr.themes.colors.stone,
    font=[gr.themes.GoogleFont("Jost"), "sans-serif"],
).set(
    body_background_fill="#FFFDF6",
    body_background_fill_dark="#FFFDF6",
    button_primary_background_fill="#6B1A2B",
    button_primary_background_fill_hover="#8A2238",
    button_primary_text_color="#FAF3E7",
)

CALPAK_CSS = """
.gradio-container { max-width: 1440px !important; margin: auto; padding: 0 20px 96px 20px !important; }
footer { display: none !important; }

/* ---- Demo storefront (markup in storefront.py) ---- */
.demo-pill {
    display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 11px;
    border: 1px solid #1A1A1A; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; color: #1A1A1A;
}
.demo-pill-dark { background: #1A1A1A; color: #FFFDF6; height: 24px; padding: 0 10px; }
#demo-ribbon {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 10px;
    width: 100vw; margin-left: calc(50% - 50vw); box-sizing: border-box;
    padding: 10px 16px; background: #F5EE7A; color: #1A1A1A;
    font-size: 15px; line-height: 1.4; text-align: center;
}
#nav-row {
    align-items: center; flex-wrap: nowrap; gap: 20px; margin-top: 16px; padding: 10px 24px;
    background: #FFFFFF; border-radius: 10px; box-shadow: 0 1px 0 #EDE8DC;
}
#nav-left-wrap { flex: 1 1 0 !important; min-width: 0 !important; }
#nav-left { display: flex; flex-wrap: wrap; align-items: center; gap: 28px; }
#wordmark-wrap { display: flex; align-items: center; gap: 10px; }
#wordmark { letter-spacing: 0.04em; font-weight: 500; font-size: 26px; color: #1A1A1A; white-space: nowrap; }
#nav-links { display: flex; flex-wrap: wrap; gap: 8px 26px; font-size: 17px; color: #1A1A1A; }
#nav-links span { cursor: default; }
#search-box { flex: 0 0 280px !important; min-width: 0 !important; }
#search-box textarea, #search-box input {
    border-radius: 999px !important; border: 1.5px solid #1A1A1A !important;
    padding: 9px 18px !important; font-size: 15px !important; background: #FFFFFF !important;
}

/* Banner: dusty rose, a lighter maroon, so the maroon launcher pill stands out. */
#hero {
    margin-top: 16px; background: #A8707A; border-radius: 14px; overflow: hidden;
    flex-wrap: wrap; gap: 0 !important; align-items: stretch;
}
#hero-copy { flex: 1 1 520px !important; padding: 56px 52px !important; gap: 0 !important; justify-content: center; }
#hero-copy-text { display: flex; flex-direction: column; gap: 18px; color: #2A0A10; }
#hero-copy-text h1 { margin: 0; font-size: 54px; line-height: 1.05; font-weight: 500; color: #2A0A10; }
#hero-copy-text p { margin: 0; font-size: 19px; line-height: 1.5; max-width: 500px; color: #2A0A10; }
.hero-tag {
    align-self: flex-start; display: inline-flex; align-items: center; height: 26px; padding: 0 12px;
    border-radius: 13px; border: 1px solid #2A0A10; font-size: 12px; font-weight: 600; letter-spacing: 0.06em;
    color: #2A0A10; white-space: nowrap;
}
#hero-ask-label { margin-top: 10px; font-size: 14px; font-weight: 500; color: #2A0A10; }
#hero-ask { max-width: 540px; margin-top: 8px; background: transparent !important; border: 0 !important; box-shadow: none !important; }
#hero-ask .input-container { display: flex; align-items: center; gap: 16px; }
#hero-ask textarea, #hero-ask input {
    border-radius: 999px !important; border: 0 !important; background: #FFFFFF !important;
    padding: 16px 22px !important; font-size: 16px !important; color: #1A1A1A !important;
}
#hero-ask button {
    position: static !important; flex: 0 0 52px; background: #F5EE7A !important; color: #1A1A1A !important;
    border-radius: 999px !important; width: 52px !important; min-width: 52px !important; height: 52px !important;
}
#hero-art {
    flex: 1 1 480px !important; min-height: 420px; background: #B37E87;
    display: flex; align-items: flex-end; justify-content: center; padding: 40px 24px 0 24px;
}
#hero-art-inner { display: flex; align-items: flex-end; justify-content: center; width: 100%; }
#hero-art-inner img { width: auto; object-fit: contain; mix-blend-mode: multiply; margin: 0; }
.hero-art-left { height: 320px; margin-right: -40px !important; }
.hero-art-mid { height: 350px; }
.hero-art-right { height: 290px; margin-left: -40px !important; }

#sf-products { margin-top: 40px; }
#sf-products-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 12px; }
#sf-products-head h2 { margin: 0; font-size: 40px; font-weight: 500; color: #1A1A1A; }
#sf-products-head span { font-size: 15px; color: #5E5A52; }
#sf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 18px; margin-top: 24px; }
.sf-tile { display: flex; flex-direction: column; gap: 12px; color: #1A1A1A !important; text-decoration: none !important; }
.sf-photo { position: relative; display: block; aspect-ratio: 3 / 4; background: #F4F5F8; border-radius: 10px; overflow: hidden; }
.sf-photo img { width: 100%; height: 100%; object-fit: contain; mix-blend-mode: multiply; margin: 0; }
.sf-off {
    position: absolute; left: 14px; top: 14px; display: inline-flex; align-items: center; height: 30px;
    padding: 0 12px; border-radius: 15px; border: 1.5px solid #B3202A; background: #FFFFFF; color: #B3202A; font-size: 14px;
}
.sf-meta { display: flex; justify-content: space-between; gap: 12px; font-size: 18px; line-height: 1.3; text-align: left; }
.sf-prices { white-space: nowrap; }
.sf-prices s { color: #5E5A52; }
#sf-footer {
    display: flex; flex-wrap: wrap; gap: 8px 32px; margin-top: 48px; padding-top: 22px;
    border-top: 1px solid #E4DFD2; font-size: 14px; line-height: 1.5; color: #4A4740;
}
.sf-footer-title { font-weight: 600; color: #1A1A1A; }

/* Narrow screens: stack the nav, shrink the banner type, drop the banner art. */
@media (max-width: 900px) {
    #nav-row { flex-wrap: wrap; }
    #search-box { flex: 1 1 100% !important; }
    #hero-copy { padding: 32px 24px !important; }
    #hero-copy-text h1 { font-size: 36px; }
    #hero-copy-text p { font-size: 17px; }
    #hero-art { display: none !important; }
    #sf-products-head h2 { font-size: 30px; }
}

/* ---- Popup chat: launcher button + floating panel, pinned bottom-left ---- */
#chat-launcher {
    position: fixed; left: 24px; bottom: 24px; z-index: 900;
    width: auto; min-width: 0; max-width: calc(100vw - 48px);
    border-radius: 999px; padding: 14px 24px; font-weight: 600; font-size: 16px;
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
