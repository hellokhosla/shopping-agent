"""OWNER: Everyone — this is the integration seam, not any one area's code.

V0 (Workflow): classify -> dispatch -> search -> format.

Code is the center of control. The model is called exactly once per message,
only to classify intent and extract constraints; every step after that is
plain Python running the same way every time.

Wires the three team areas together without any of them importing each other:
  backend/   (Gaurav, Prasad)  -> load_catalog()
  middle/    (Kapil, Kavya)    -> classify(), DISPATCH, clamp_price()
  frontend/  (Jasmeet, Carly)  -> format_rows(), build_demo()
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from backend.catalog import load_catalog
from frontend.theme import CALPAK_CSS, CALPAK_THEME
from frontend.ui import build_demo, format_rows
from middle.classify import classify
from middle.dispatch import DISPATCH
from middle.guardrails import clamp_price


def respond(message: str) -> str:
    intent = classify(message)
    intent.max_price = clamp_price(intent.max_price)

    catalog = load_catalog()
    handler = DISPATCH[intent.objective]
    rows = handler(catalog, intent)

    answer = format_rows(rows)
    debug = f"\n\n<sub>_intent: {intent.objective} · category={intent.category} · brand={intent.brand} · max_price={intent.max_price}_</sub>"
    return answer + debug


demo = build_demo(respond)

if __name__ == "__main__":
    demo.launch(theme=CALPAK_THEME, css=CALPAK_CSS, share=True)
