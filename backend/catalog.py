"""Catalog ingestion and offline enrichment (PRD M2, M3).

Loads a retailer CSV through its field mapping, normalizes products into the
shared model, enriches colors and only synthesizes stock when the source lacks it.
"""

from __future__ import annotations

import hashlib
import pickle
import random
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Iterable, overload

import pandas as pd

from .colors import COLOR_LOOKUPS
from .configuration import DataEnrichmentConfig, RetailerConfig
from .category_rules import CategoryRule
from .models import ONE_SIZE, Product

CACHE_DIR = Path(__file__).resolve().parent / ".cache"


class Catalog:
    """In-memory catalog with a tag index for fast category pre-filtering."""

    def __init__(self, products: Iterable[Product], retailer: RetailerConfig, enrichment: DataEnrichmentConfig):
        self.products = list(products)
        self.by_sku = {p.sku: p for p in self.products}
        self.retailer = retailer
        self.enrichment = enrichment
        self._by_tag: dict[str, list[Product]] = defaultdict(list)
        for product in self.products:
            for tag in product.tags:
                self._by_tag[tag].append(product)

    def __len__(self) -> int:
        return len(self.products)

    def category_rule(self, category: str | None, semantic_terms: Iterable[str] = ()) -> CategoryRule | None:
        if not category:
            return None
        return CategoryRule(
            tags=frozenset(self.retailer.category_tags.get(category, [])),
            semantic_terms=tuple(term.strip().lower() for term in semantic_terms if term.strip()),
        )

    def candidates(self, rule: CategoryRule | None) -> list[Product]:
        """Cheap pre-filter by tag; the matching engine re-checks every rule."""
        if rule is None:
            return self.products
        seen: dict[str, Product] = {}
        for tag in rule.tags:
            for product in self._by_tag.get(tag, []):
                seen.setdefault(product.sku, product)
        return list(seen.values())


def _synthetic_stock(sku: str, size_system: str, sizes: list[str], seed: int, in_stock_rate: float):
    # Seeded per SKU so stock is reproducible regardless of load order (labelled synthetic in the UI).
    rng = random.Random(zlib.crc32(sku.encode()) ^ seed)
    if size_system == "one_size":
        return ((ONE_SIZE, rng.randint(1, 20) if rng.random() < max(in_stock_rate, 0.9) else 0),)
    return tuple((size, rng.randint(1, 12) if rng.random() < in_stock_rate else 0) for size in sizes)


def _to_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None  # drop NaN


def _source_available(value: object) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "available", "in stock"}:
        return True
    if normalized in {"false", "0", "no", "unavailable", "out of stock", ""}:
        return False
    raise ValueError(f"Unrecognized source availability value: {value!r}")


def build_products(df: pd.DataFrame, retailer: RetailerConfig, enrichment: DataEnrichmentConfig) -> list[Product]:
    src = retailer.catalog
    mapping = src.field_mapping
    df = df.rename(columns={v: k for k, v in mapping.items()})[list(mapping)]
    df = df.fillna("")
    df["sku"] = df["sku"].astype(str).str.strip()

    df = df[~df["category"].isin(src.drop_categories)]
    dropped_skus = set(df.loc[df["tag"].isin(src.drop_skus_with_tags), "sku"])
    df = df[~df["sku"].isin(dropped_skus)]

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df[(df["price"] > 0) & (df["price"] <= src.max_valid_price)]

    separator = src.tag_separator
    tags = df.groupby("sku")["tag"].agg(
        lambda values: frozenset(
            tag.strip()
            for value in values
            for tag in (str(value).split(separator) if separator else [str(value)])
            if tag.strip()
        )
    )
    first = df.drop_duplicates("sku").set_index("sku")

    color_fn = COLOR_LOOKUPS[src.color_lookup]
    products: list[Product] = []
    for sku, row in first.iterrows():
        family, shade = color_fn(str(row["color_code"]))
        size_system = src.size_system_by_category.get(row["category"], "one_size")
        stock_is_synthetic = src.stock_mode == "synthetic"
        if stock_is_synthetic:
            stock = _synthetic_stock(
                sku, size_system, enrichment.size_systems.get(size_system, []), src.stock_seed, src.in_stock_rate
            )
        else:
            size_value = src.size_value_by_category.get(row["category"], ONE_SIZE)
            stock = ((size_value, int(_source_available(row["available"]))),)
        rating = _to_float(row.get("rating"))
        count = _to_float(row.get("review_count")) or 0
        was = _to_float(row.get("was_price"))
        raw_tags = tags[sku]
        category_tag = str(row["category"]).strip()
        products.append(
            Product(
                sku=sku,
                name=str(row["name"]).strip(),
                brand=(src.brand_override or str(row["brand"])).strip(),
                price=round(float(row["price"]), 2),
                category=str(row["category"]),
                tags=raw_tags | ({category_tag} if category_tag else set()),
                color_code=str(row["color_code"]),
                color_family=family,
                color_shade=shade,
                size_system=size_system,
                stock=stock,
                description=str(row.get("description") or "").strip(),
                stock_is_synthetic=stock_is_synthetic,
                was_price=was if was and was > row["price"] else None,
                promotion=str(row.get("promotion") or "").strip() or None,
                rating=rating if rating and count > 0 else None,
                review_count=int(count),
            )
        )
    return products


@overload
def load_catalog() -> pd.DataFrame: ...


@overload
def load_catalog(retailer: RetailerConfig, enrichment: DataEnrichmentConfig, use_cache: bool = True) -> Catalog: ...


def load_catalog(
    retailer: RetailerConfig | None = None,
    enrichment: DataEnrichmentConfig | None = None,
    use_cache: bool = True,
) -> Catalog | pd.DataFrame:
    if retailer is None and enrichment is None:
        from .legacy_catalog import load_catalog as load_legacy_catalog

        return load_legacy_catalog()
    if retailer is None or enrichment is None:
        raise ValueError("Both retailer and enrichment are required for an enriched catalog.")
    csv_path = retailer.catalog_path
    fingerprint = hashlib.sha1(
        f"{csv_path.stat().st_mtime_ns}|{retailer.model_dump_json()}|{enrichment.model_dump_json()}".encode()
    ).hexdigest()[:12]
    cache_file = CACHE_DIR / f"{retailer.retailer_id}_{fingerprint}.pkl"

    if use_cache and cache_file.exists():
        with cache_file.open("rb") as fh:
            products = pickle.load(fh)
    else:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        products = build_products(df, retailer, enrichment)
        if use_cache:
            CACHE_DIR.mkdir(exist_ok=True)
            for old in CACHE_DIR.glob(f"{retailer.retailer_id}_*.pkl"):
                old.unlink()
            with cache_file.open("wb") as fh:
                pickle.dump(products, fh)
    return Catalog(products, retailer, enrichment)
