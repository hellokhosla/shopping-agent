"""OWNER: Gaurav, Prasad — Backend (data ingestion, catalog storage, metadata).

Loads the real Calpak catalog once per process. Plain pandas, no model involved.
This is the seam to widen if/when a second retailer (e.g. Nordstrom) or a
different storage layer (MCP, API, data warehouse) gets added.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_PATH = Path(__file__).parent.parent / "data" / "calpak_catalog_variants.csv"

_catalog: pd.DataFrame | None = None


def load_catalog() -> pd.DataFrame:
    global _catalog
    if _catalog is None:
        df = pd.read_csv(
            DATA_PATH,
            usecols=[
                "product_id",
                "title",
                "product_type",
                "price",
                "compare_at_price",
                "available",
                "product_url",
                "image_url",
                "description_text",
            ],
        )
        df["available"] = df["available"].astype(str).str.lower() == "true"
        df = df[df["available"]].drop_duplicates(subset="product_id").reset_index(drop=True)
        _catalog = df
    return _catalog
