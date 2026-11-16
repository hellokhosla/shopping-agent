"""OWNER: Kapil, Kavya — Middle (model selection, guardrails, intent routing).

Intent classification — the only place the model runs in V0 (workflow).
Everything downstream of this reads intent.objective and dispatches to plain
code; the model never touches the catalog or decides how results are shaped.
"""

from __future__ import annotations

from typing import Literal, Optional

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field


class ShoppingIntent(BaseModel):
    objective: Literal["cross_category", "single_category", "specific_product", "branded"] = Field(
        description=(
            "cross_category: broad/undecided ('a gift for my dad'). "
            "single_category: knows the category, not the product ('best carry-on under $150'). "
            "specific_product: names an exact item ('the Trek Duffel 26L'). "
            "branded: wants a specific brand's lineup ('Calpak bags')."
        )
    )
    category: Optional[str] = Field(None, description="Product category/type, e.g. 'bags', 'luggage', 'accessories'")
    product_query: Optional[str] = Field(None, description="Exact product name or phrase, if the shopper named one")
    brand: Optional[str] = Field(None, description="Brand or style/collection keyword, if mentioned")
    max_price: Optional[float] = Field(None, description="Hard price ceiling if the shopper gave one")


_classifier = None


def get_classifier():
    global _classifier
    if _classifier is None:
        llm = ChatAnthropic(model="claude-haiku-5-5")
        _classifier = llm.with_structured_output(ShoppingIntent)
    return _classifier


def classify(query: str) -> ShoppingIntent:
    return get_classifier().invoke(query)
