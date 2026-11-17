"""OWNER: Jasmeet, Carly — Frontend (customer engagement / UI).

Static markup for the demo storefront that sits behind the chat panel: the
demo ribbon, nav, banner copy and art, a product row, and the footer.

It is deliberately a *demo* storefront: a ribbon and DEMO tags say it is a
course project, not affiliated with CALPAK, and the banner is an original
graphic rather than CALPAK's campaign photography. Product names, photos and
prices are a 15 Nov 2026 snapshot of CALPAK's public catalog, hard-coded here
so the frontend never reads Backend data directly.
"""

from __future__ import annotations

import html

_CDN = "https://cdn.shopify.com/s/files/1/0941/4996/files/"
_SHOP = "https://www.calpaktravel.com/products/"


def _img(file: str, width: int) -> str:
    return f"{_CDN}{file}&width={width}"


RIBBON_HTML = """
<div id="demo-ribbon">
  <span class="demo-pill demo-pill-dark">DEMO</span>
  <span>Course project storefront. Not affiliated with or endorsed by CALPAK.
  Prices and stock are from a 15 Nov 2026 catalog snapshot; nothing here can be bought.</span>
</div>
"""

NAV_LEFT_HTML = """
<div id="nav-left">
  <div id="wordmark-wrap">
    <span id="wordmark">CALPAK</span>
    <span class="demo-pill">DEMO</span>
  </div>
  <div id="nav-links">
    <span>Shop All</span><span>Best Sellers</span><span>Bags</span>
    <span>Luggage</span><span>Organizers &amp; More</span><span>Gifts</span>
  </div>
</div>
"""

HERO_COPY_HTML = """
<div id="hero-copy-text">
  <span class="hero-tag">SHOPPING AGENT DEMO</span>
  <h1>Tell us about the trip.<br>We'll find the bag.</h1>
  <p>Describe where you're going, who it's for and what you want to spend.
  The assistant picks a few products from the catalog and says why.</p>
  <span id="hero-ask-label">Ask the shopping assistant</span>
</div>
"""

_HERO_ART = [
    ("AMBEUR-LARGE-LUGGAGE-FRONT-METALLIC-RED.jpg?v=1738958552", "hero-art-left"),
    ("LVT1028_VAULT_LARGE_DARKCHERRY_1.jpg?v=1784941420", "hero-art-mid"),
    ("LHU1028_HUE_LARGE_GLAZEDCHERRY_1.jpg?v=1770839460", "hero-art-right"),
]
HERO_ART_HTML = (
    '<div id="hero-art-inner">'
    + "".join(f'<img class="{cls}" src="{_img(f, 600)}" alt="">' for f, cls in _HERO_ART)
    + "</div>"
)

# (name, photo alt, image file, compare-at price, price, product page path)
_PICKS = [
    ("Ambeur Large Luggage", "Ambeur Large Luggage in Metallic Red",
     "AMBEUR-LARGE-LUGGAGE-FRONT-METALLIC-RED.jpg?v=1738958552", "$325", "$260",
     "ambeur-large-luggage?variant=40771030319162"),
    ("Hue Large Luggage", "Hue Large Luggage in Glazed Dark Cherry",
     "LHU1028_HUE_LARGE_GLAZEDCHERRY_1.jpg?v=1770839460", "$295", "$236",
     "hue-large-luggage?variant=41013495889978"),
    ("Vault Large Luggage", "Vault Large Luggage in Dark Cherry",
     "LVT1028_VAULT_LARGE_DARKCHERRY_1.jpg?v=1784941420", "$525", "$420",
     "vault-large-luggage?variant=41309730209850"),
    ("Packing Cubes Set (5 Pieces)", "Packing Cubes Set in Dark Cherry",
     "PC1601_PACKING-CUBES_DARKCHERRY_1.jpg?v=1785344625", "$68", "$54.40",
     "packing-cubes-5-piece-set?variant=41307855880250"),
]


def _pick(name, alt, file, was, price, path) -> str:
    url = html.escape(_SHOP + path, quote=True)
    return (
        f'<a class="sf-tile" href="{url}" target="_blank" rel="noopener">'
        f'<span class="sf-photo"><img src="{_img(file, 640)}" alt="{html.escape(alt)}" loading="lazy">'
        '<span class="sf-off">20% Off</span></span>'
        f'<span class="sf-meta"><span>{html.escape(name)}</span>'
        f'<span class="sf-prices"><s>{was}</s> {price}</span></span>'
        "</a>"
    )


PRODUCTS_HTML = (
    '<div id="sf-products">'
    '<div id="sf-products-head"><h2>Picked from the catalog</h2>'
    "<span>Sample products from the demo catalog</span></div>"
    '<div id="sf-grid">' + "".join(_pick(*p) for p in _PICKS) + "</div></div>"
)

FOOTER_HTML = """
<div id="sf-footer">
  <span class="sf-footer-title">About this demo</span>
  <span>Team 12 retail shopping agent, V0 workflow. The model classifies intent once per
  message; code does everything else: search, price limits and formatting. Product names,
  photos and prices belong to CALPAK and are used here for a class demo only.</span>
</div>
"""
