"""OWNER: Kapil, Kavya — Middle (model selection, guardrails, intent routing).

Dispatch table: the classification label picks which plain function shapes
the catalog results. No model involved past classify.py — every function here
is deterministic filtering over the same DataFrame.
"""

from __future__ import annotations

import pandas as pd

from .classify import ShoppingIntent
from .guardrails import clamp_results


def show_category_overview(catalog: pd.DataFrame, intent: ShoppingIntent) -> pd.DataFrame:
    """Cross-category: broad request, show a couple of picks per matching category."""
    rows = catalog
    if intent.category:
        rows = rows[rows["product_type"].str.contains(intent.category, case=False, na=False)]
    if intent.max_price is not None:
        rows = rows[rows["price"] <= intent.max_price]
    overview = rows.groupby("product_type", group_keys=False)[rows.columns].apply(lambda g: g.head(2))
    return clamp_results(overview)


def show_tiers(catalog: pd.DataFrame, intent: ShoppingIntent) -> pd.DataFrame:
    """Single-category: one category, split into low/mid/premium price bands.

    A hard price ceiling always wins over the tiering: if the shopper gave a
    budget, no row above it is ever returned, even if that collapses the
    premium band to nothing.
    """
    rows = catalog
    if intent.category:
        rows = rows[rows["product_type"].str.contains(intent.category, case=False, na=False)]
    if intent.max_price is not None:
        rows = rows[rows["price"] <= intent.max_price]
    bands = [(0, 50), (50, 150), (150, 10_000)]
    tiers = [rows[(rows["price"] >= lo) & (rows["price"] < hi)].head(2) for lo, hi in bands]
    return clamp_results(pd.concat(tiers))


def lookup_exact_product(catalog: pd.DataFrame, intent: ShoppingIntent) -> pd.DataFrame:
    """Specific product: exact-ish title match, no grouping."""
    query = (intent.product_query or "").strip()
    if not query:
        return catalog.head(0)
    rows = catalog[catalog["title"].str.contains(query, case=False, na=False)]
    return clamp_results(rows)


def show_brand_lineup(catalog: pd.DataFrame, intent: ShoppingIntent) -> pd.DataFrame:
    """Branded: filter by brand/style keyword (title or description), cheapest first."""
    rows = catalog
    if intent.brand:
        keyword = intent.brand
        rows = rows[
            rows["title"].str.contains(keyword, case=False, na=False)
            | rows["description_text"].str.contains(keyword, case=False, na=False)
        ]
    if intent.max_price is not None:
        rows = rows[rows["price"] <= intent.max_price]
    return clamp_results(rows.sort_values("price"))


DISPATCH = {
    "cross_category": show_category_overview,
    "single_category": show_tiers,
    "specific_product": lookup_exact_product,
    "branded": show_brand_lineup,
}
