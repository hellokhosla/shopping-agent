"""Prepare enriched retailer catalogs and load them into PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

from .configuration import RetailerConfig, load_retailer
from .models import Product

from .catalog import build_products
from .database_config import load_database_environment

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
RETAILER_CONFIG_DIR = Path(__file__).resolve().parent / "config" / "retailers"

_COLOR_FAMILIES = {
    "black/grey": "black_grey",
    "white": "white",
    "brown": "brown",
    "green": "green",
    "blue": "blue",
    "purple": "purple",
    "red/pink": "red_pink",
    "yellow/gold": "yellow_gold",
    "orange": "orange",
    "multi": "multi",
}
_INTERNAL_TAG_PATTERNS = (
    re.compile(r"^(?:BFCM|LDS|MDS|DAD)\d+", re.IGNORECASE),
    re.compile(r"^pc-\d+$", re.IGNORECASE),
    re.compile(r"^ycrf_reviews-", re.IGNORECASE),
    re.compile(r"^(?:allproducts|hotdeals?|increase\d+)$", re.IGNORECASE),
    re.compile(r"^hotdeal\d+$", re.IGNORECASE),
)
_NORDSTROM_DEPARTMENTS = {
    "clothing": "clothing",
    "maternity": "clothing",
    "shoes": "shoes",
    "handbags": "bags",
    "accessories": "accessories",
    "jewelry": "accessories",
}
_CALPAK_DEPARTMENTS = {
    "Mini Carry-On Luggage": "luggage",
    "Carry-On Luggage": "luggage",
    "Medium Luggage": "luggage",
    "Large Luggage": "luggage",
    "Luggage Sets": "luggage",
    "Backpack": "bags",
    "Duffel": "bags",
    "Crossbodies & Belt Bags": "bags",
    "Tote": "bags",
    "Diaper Bags": "bags",
    "Insulated Bags": "bags",
    "Toiletry, Makeup & Jewelry Bags": "bags",
    "Packing Cubes": "accessories",
    "Organizers & Laptop Sleeves": "accessories",
    "Wallets & Pouches": "accessories",
    "Travel Accessories": "accessories",
    "Personalization Accessories": "accessories",
    "CALPAK Merchandise": "accessories",
}
_LUGGAGE_SIZE_CLASSES = {
    "Mini Carry-On Luggage": "mini_carry_on",
    "Carry-On Luggage": "carry_on",
    "Medium Luggage": "medium",
    "Large Luggage": "large",
    "Luggage Sets": "set",
}
_NORDSTROM_TYPE_HINTS = {
    "blazer": ("blazer", "suit jacket", "sport coat"),
    "pants": ("pants", "trousers", "slacks", "suit pant"),
    "hiking boots": ("hiking boots", "hiking boot"),
    "rain jacket": ("rain jacket", "raincoat", "anorak"),
}
_PRODUCT_COLUMNS = (
    "retailer_id",
    "external_id",
    "title",
    "brand",
    "product_line",
    "department",
    "product_type",
    "source_categories",
    "tags",
    "description",
    "best_for",
    "features",
    "attrs",
    "occasion_tags",
    "style_tags",
    "size_class",
    "rating",
    "review_count",
    "promotion",
    "image_url",
    "product_url",
    "search_text",
    "embedding",
    "embedding_model",
    "embedded_at",
    "synthetic_flags",
    "is_active",
    "source_payload",
)
_VARIANT_COLUMNS = (
    "retailer_id",
    "product_external_id",
    "external_variant_id",
    "sku",
    "colour_raw",
    "colour_family",
    "colour_shade",
    "size_label",
    "size_norm",
    "price",
    "was_price",
    "in_stock",
    "image_url",
    "variant_url",
)
_JSON_COLUMNS = {"attrs", "source_payload"}


@dataclass(frozen=True)
class RetailerBatch:
    retailer_id: str
    display_name: str
    help_page_url: str
    config_snapshot: dict[str, Any]
    config_hash: str
    products: list[dict[str, Any]]
    variants: list[dict[str, Any]]


def _ordered_unique(values: Iterable[object]) -> list[str]:
    result: dict[str, None] = {}
    for value in values:
        normalized = str(value).strip()
        if normalized:
            result.setdefault(normalized, None)
    return list(result)


def _optional_text(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _normalize_word(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith(("sses", "xes", "ches", "shes")) and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _size_norm(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"", "ONE SIZE", "ONE_SIZE"}:
        return "ONE_SIZE"
    return re.sub(r"\s+", "_", normalized)


def _colour_family(value: str) -> str:
    try:
        return _COLOR_FAMILIES[value]
    except KeyError as exc:
        raise ValueError(f"Unmapped normalized colour family: {value!r}") from exc


def _clean_tags(values: Iterable[str]) -> list[str]:
    cleaned: dict[str, None] = {}
    for value in values:
        tag = value.strip()
        if not tag or any(pattern.match(tag) for pattern in _INTERNAL_TAG_PATTERNS):
            continue
        cleaned.setdefault(tag, None)
    return list(cleaned)


def _department(retailer_id: str, source_category: str) -> str:
    if retailer_id == "nordstrom":
        try:
            return _NORDSTROM_DEPARTMENTS[source_category.strip().lower()]
        except KeyError as exc:
            raise ValueError(f"Unmapped Nordstrom department: {source_category!r}") from exc
    if retailer_id == "calpak":
        try:
            return _CALPAK_DEPARTMENTS[source_category]
        except KeyError as exc:
            raise ValueError(f"Unmapped CALPAK department: {source_category!r}") from exc
    raise ValueError(f"Unsupported retailer: {retailer_id!r}")


def _nordstrom_product_type(
    title: str, source_categories: list[str], category_tags: dict[str, list[str]]
) -> str:
    available_categories = {
        product_type
        for product_type, source_tags in category_tags.items()
        if set(source_categories).intersection(source_tags)
    }
    if not available_categories:
        return _slug(source_categories[0]) if source_categories else "other"

    normalized_title = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
    hinted_categories = {
        product_type: max(
            (len(hint.split()) for hint in _NORDSTROM_TYPE_HINTS.get(product_type, (product_type,))),
            default=0,
        )
        for product_type in available_categories
        if any(
            re.search(rf"\b{re.escape(hint)}\b", normalized_title)
            for hint in _NORDSTROM_TYPE_HINTS.get(product_type, (product_type,))
        )
    }
    if hinted_categories:
        return _slug(max(hinted_categories, key=lambda value: (hinted_categories[value], len(value))))
    specific_categories = {
        product_type
        for product_type, source_tags in category_tags.items()
        if any(
            tag in source_categories
            and sum(tag in candidate_tags for candidate_tags in category_tags.values()) == 1
            for tag in source_tags
        )
    }
    if len(specific_categories) == 1:
        return _slug(next(iter(specific_categories)))
    if len(available_categories) == 1:
        return _slug(next(iter(available_categories)))

    title_words = set(normalized_title.split())

    def score(product_type: str) -> tuple[int, int, str]:
        words = re.findall(r"[a-z0-9]+", product_type.lower())
        normalized_words = {_normalize_word(word) for word in words}
        normalized_title = {_normalize_word(word) for word in title_words}
        matches = len(normalized_words.intersection(normalized_title))
        return matches, len(words), product_type

    best = max(available_categories, key=score)
    if score(best)[0]:
        return _slug(best)
    return _slug(source_categories[0]) if source_categories else _slug(best)


def _best_for_and_features(description: str) -> tuple[str | None, list[str]]:
    best_for_match = re.search(
        r"\bBest for:\s*(.*?)(?=\s+Features:|$)", description, flags=re.IGNORECASE | re.DOTALL
    )
    best_for = _optional_text(best_for_match.group(1)) if best_for_match else None
    features_match = re.search(r"\bFeatures:\s*(.*)$", description, flags=re.IGNORECASE | re.DOTALL)
    if not features_match:
        return best_for, []

    features: list[str] = []
    for sentence in re.split(r"(?<=\.)\s+", features_match.group(1).strip()):
        heading, separator, _ = sentence.partition(":")
        if separator and heading.strip():
            features.append(heading.strip())
    return best_for, features


def _attributes(description: str) -> dict[str, int]:
    match = re.search(
        r"\b(?:fits?|accommodates?)\s+(?:laptops?\s+)?(?:up to\s+)?(\d{1,2})\s*(?:inches|inch|in\.|[\"″])\s*(?:laptop)?",
        description,
        flags=re.IGNORECASE,
    )
    return {"laptop_in": int(match.group(1))} if match else {}


def _product_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key.lower() != "variant"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _search_text(
    *,
    title: str,
    brand: str | None,
    product_line: str | None,
    product_type: str,
    source_categories: list[str],
    colours: list[str],
    tags: list[str],
    occasion_tags: list[str],
    style_tags: list[str],
    best_for: str | None,
    description: str | None,
) -> str:
    parts = [title]
    for label, value in (
        ("Brand", brand),
        ("Line", product_line),
        ("Type", product_type),
        ("Categories", "; ".join(source_categories) or None),
        ("Colours", "; ".join(colours) or None),
        ("Tags", "; ".join(tags) or None),
        ("Occasion", "; ".join(occasion_tags) or None),
        ("Style", "; ".join(style_tags) or None),
        ("Best for", best_for),
    ):
        if value:
            parts.append(f"{label}: {value}")
    if description:
        parts.append(description[:500].strip())
    return ". ".join(part for part in parts if part)


def _raw_rows_by_key(frame: pd.DataFrame, key_column: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for key, group in frame.groupby(key_column, sort=False, dropna=False):
        normalized_key = str(key).strip()
        if normalized_key:
            result[normalized_key] = group.drop(columns=["_db_sku"], errors="ignore").to_dict(
                orient="records"
            )
    return result


def _config_snapshot(config_path: Path, retailer: RetailerConfig) -> tuple[dict[str, Any], str]:
    retailer_config = json.loads(config_path.read_text(encoding="utf-8"))
    category_pack_path = (
        config_path.parent.parent / "category_packs" / f"{retailer.category_pack}.json"
    )
    category_pack = json.loads(category_pack_path.read_text(encoding="utf-8"))
    snapshot = {"retailer": retailer_config, "category_pack": category_pack}
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot, f"sha256:{digest}"


def _base_product_record(
    retailer: RetailerConfig,
    product: Product,
    external_id: str,
    source_categories: list[str],
    raw_rows: list[dict[str, str]],
    *,
    product_line: str | None = None,
    tags: list[str] | None = None,
    image_url: str | None = None,
    product_url: str | None = None,
    colours: list[str] | None = None,
    size_class: str | None = None,
) -> dict[str, Any]:
    description = _optional_text(product.description)
    best_for, features = _best_for_and_features(description or "")
    occasion_tags: list[str] = []
    style_tags: list[str] = []
    synthetic_flags = ["sizes", "stock"] if product.stock_is_synthetic else []
    if retailer.retailer_id == "nordstrom":
        source_department = next(
            (row.get(retailer.catalog.field_mapping["category"], "") for row in raw_rows),
            product.category,
        )
        department = _department(retailer.retailer_id, source_department)
        product_type = _nordstrom_product_type(
            product.name, source_categories, retailer.category_tags
        )
    else:
        department = _department(retailer.retailer_id, product.category)
        product_type = _slug(product.category)

    promotion = product.promotion
    if not promotion and product.was_price and product.was_price > product.price:
        promotion = "Sale"

    return {
        "retailer_id": retailer.retailer_id,
        "external_id": external_id,
        "title": product.name,
        "brand": _optional_text(product.brand),
        "product_line": product_line,
        "department": department,
        "product_type": product_type,
        "source_categories": source_categories,
        "tags": tags or [],
        "description": description,
        "best_for": best_for,
        "features": features,
        "attrs": _attributes(description or ""),
        "occasion_tags": occasion_tags,
        "style_tags": style_tags,
        "size_class": size_class,
        "rating": product.rating,
        "review_count": product.review_count if product.rating is not None else None,
        "promotion": promotion,
        "image_url": image_url,
        "product_url": product_url,
        "search_text": _search_text(
            title=product.name,
            brand=_optional_text(product.brand),
            product_line=product_line,
            product_type=product_type,
            source_categories=source_categories,
            colours=colours or [],
            tags=tags or [],
            occasion_tags=occasion_tags,
            style_tags=style_tags,
            best_for=best_for,
            description=description,
        ),
        "embedding": None,
        "embedding_model": None,
        "embedded_at": None,
        "synthetic_flags": synthetic_flags,
        "is_active": True,
        "source_payload": raw_rows,
    }


def prepare_retailer_batch(config_path: str | Path) -> RetailerBatch:
    """Run the existing enrichment pipeline and map its output to DB products/variants."""
    config_path = Path(config_path).resolve()
    retailer, enrichment = load_retailer(config_path)
    source = pd.read_csv(retailer.catalog_path, dtype=str, keep_default_na=False)
    products = build_products(source, retailer, enrichment)
    source_sku_column = retailer.catalog.field_mapping["sku"]
    source["_db_sku"] = source[source_sku_column].astype(str).str.strip()
    accepted_skus = {product.sku for product in products}
    accepted_source = source[source["_db_sku"].isin(accepted_skus)].copy()
    source_category_column = retailer.catalog.field_mapping.get("category")
    if source_category_column:
        accepted_source = accepted_source[
            ~accepted_source[source_category_column].isin(retailer.catalog.drop_categories)
        ]
    source_price_column = retailer.catalog.field_mapping["price"]
    source_prices = pd.to_numeric(accepted_source[source_price_column], errors="coerce")
    accepted_source = accepted_source[
        (source_prices > 0) & (source_prices <= retailer.catalog.max_valid_price)
    ]
    rows_by_sku = _raw_rows_by_key(accepted_source, "_db_sku")
    products_by_sku = {product.sku: product for product in products}

    config_snapshot, config_hash = _config_snapshot(config_path, retailer)
    product_records: list[dict[str, Any]] = []
    variant_records: list[dict[str, Any]] = []

    if retailer.retailer_id == "nordstrom":
        category_column = retailer.catalog.field_mapping["tag"]
        for product in products:
            raw_rows = rows_by_sku.get(product.sku, [])
            source_categories = _ordered_unique(row.get(category_column, "") for row in raw_rows)
            product_records.append(
                _base_product_record(
                    retailer,
                    product,
                    product.sku,
                    source_categories,
                    raw_rows,
                    colours=[product.color_shade or product.color_family],
                )
            )
            family = _colour_family(product.color_family)
            for size_label, quantity in product.stock:
                variant_records.append(
                    {
                        "retailer_id": retailer.retailer_id,
                        "product_external_id": product.sku,
                        "external_variant_id": None,
                        "sku": product.sku,
                        "colour_raw": _optional_text(product.color_code),
                        "colour_family": family,
                        "colour_shade": _optional_text(product.color_shade),
                        "size_label": size_label,
                        "size_norm": _size_norm(size_label),
                        "price": product.price,
                        "was_price": product.was_price,
                        "in_stock": quantity > 0,
                        "image_url": None,
                        "variant_url": None,
                    }
                )
    elif retailer.retailer_id == "calpak":
        required_columns = {"product_id", "variant_id", "image_url", "product_url"}
        missing_columns = required_columns - set(accepted_source.columns)
        if missing_columns:
            raise ValueError(f"CALPAK source is missing required columns: {sorted(missing_columns)}")

        source_category_column = retailer.catalog.field_mapping["category"]
        brand_column = retailer.catalog.field_mapping.get("brand")
        variant_rows = accepted_source.drop_duplicates(subset=["_db_sku"], keep="first")
        rows_by_product_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        variants_by_product_id: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in variant_rows.to_dict(orient="records"):
            external_id = str(row["product_id"]).strip()
            rows_by_product_id[external_id].append(
                {key: value for key, value in row.items() if key != "_db_sku"}
            )
            variants_by_product_id[external_id].append(row)

        for external_id, raw_rows in rows_by_product_id.items():
            group_products = [
                products_by_sku[str(row["_db_sku"])]
                for row in variants_by_product_id[external_id]
                if str(row["_db_sku"]) in products_by_sku
            ]
            if not group_products:
                continue
            product = group_products[0]
            source_categories = _ordered_unique(
                row.get(source_category_column, "") for row in raw_rows
            )
            clean_tags = _clean_tags(tag for item in group_products for tag in item.tags)
            color_labels = _ordered_unique(
                item.color_shade or item.color_family for item in group_products
            )
            first_row = variants_by_product_id[external_id][0]
            raw_vendor = (
                _optional_text(first_row.get(brand_column, "")) if brand_column else None
            )
            if raw_vendor and raw_vendor.lower() in {"-", "calpak"}:
                raw_vendor = None
            source_type = str(first_row.get(source_category_column, "")).strip()
            product_records.append(
                _base_product_record(
                    retailer,
                    product,
                    external_id,
                    source_categories,
                    raw_rows,
                    product_line=raw_vendor,
                    tags=clean_tags,
                    image_url=_optional_text(first_row.get("image_url")),
                    product_url=_product_url(_optional_text(first_row.get("product_url"))),
                    colours=color_labels,
                    size_class=_LUGGAGE_SIZE_CLASSES.get(source_type),
                )
            )

        for external_id, raw_rows in variants_by_product_id.items():
            for row in raw_rows:
                product = products_by_sku.get(str(row["_db_sku"]))
                if product is None:
                    continue
                size_system_value = product.stock[0][0] if product.stock else "ONE SIZE"
                if product.size_system == "one_size":
                    size_label = None
                    size_norm = "ONE_SIZE"
                else:
                    size_label = size_system_value
                    size_norm = _size_norm(size_system_value)
                variant_records.append(
                    {
                        "retailer_id": retailer.retailer_id,
                        "product_external_id": external_id,
                        "external_variant_id": _optional_text(row.get("variant_id")),
                        "sku": product.sku,
                        "colour_raw": _optional_text(product.color_code),
                        "colour_family": _colour_family(product.color_family),
                        "colour_shade": _optional_text(product.color_shade),
                        "size_label": size_label,
                        "size_norm": size_norm,
                        "price": product.price,
                        "was_price": product.was_price,
                        "in_stock": product.in_stock,
                        "image_url": _optional_text(row.get("image_url")),
                        "variant_url": _optional_text(row.get("product_url")),
                    }
                )
    else:
        raise ValueError(f"Unsupported retailer for database loading: {retailer.retailer_id}")

    return RetailerBatch(
        retailer_id=retailer.retailer_id,
        display_name=retailer.display_name,
        help_page_url=retailer.guardrails.help_page_url,
        config_snapshot=config_snapshot,
        config_hash=config_hash,
        products=product_records,
        variants=variant_records,
    )


def prepare_all_batches() -> list[RetailerBatch]:
    return [
        prepare_retailer_batch(RETAILER_CONFIG_DIR / f"{retailer_id}.json")
        for retailer_id in ("nordstrom", "calpak")
    ]


def _copy_rows(cursor: Any, table: str, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    from psycopg.types.json import Jsonb

    column_sql = ", ".join(columns)
    with cursor.copy(f"COPY {table} ({column_sql}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(
                tuple(Jsonb(row[column]) if column in _JSON_COLUMNS else row[column] for column in columns)
            )


def _apply_migrations(cursor: Any, reset: bool) -> None:
    if reset:
        cursor.execute(
            """
            DROP TABLE IF EXISTS cart_items;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS review_cache;
            DROP TABLE IF EXISTS airline_limits;
            DROP TABLE IF EXISTS size_class_dims;
            DROP TABLE IF EXISTS variants;
            DROP TABLE IF EXISTS products;
            DROP TABLE IF EXISTS retailers;
            DROP TABLE IF EXISTS schema_migrations;
            DROP FUNCTION IF EXISTS arr_text(text[]);
            """
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version text PRIMARY KEY,
          checksum text NOT NULL,
          applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = migration_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        cursor.execute(
            "SELECT checksum FROM schema_migrations WHERE version = %s",
            (migration_path.name,),
        )
        applied = cursor.fetchone()
        if applied:
            if applied[0] != checksum:
                raise RuntimeError(
                    f"Applied migration {migration_path.name} was edited. Add a new migration "
                    "or rerun with --reset --yes to rebuild the managed schema."
                )
            continue
        cursor.execute(sql)
        cursor.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
            (migration_path.name, checksum),
        )


def _upsert_retailer(cursor: Any, batch: RetailerBatch) -> None:
    from psycopg.types.json import Jsonb

    cursor.execute(
        """
        INSERT INTO retailers (retailer_id, display_name, config, config_hash, help_page_url)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (retailer_id) DO UPDATE SET
          display_name = EXCLUDED.display_name,
          config = EXCLUDED.config,
          config_hash = EXCLUDED.config_hash,
          help_page_url = EXCLUDED.help_page_url,
          loaded_at = now()
        """,
        (
            batch.retailer_id,
            batch.display_name,
            Jsonb(batch.config_snapshot),
            batch.config_hash,
            batch.help_page_url,
        ),
    )


def _create_staging_tables(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TEMP TABLE stage_products (
          retailer_id text NOT NULL,
          external_id text NOT NULL,
          title text NOT NULL,
          brand text,
          product_line text,
          department text NOT NULL,
          product_type text NOT NULL,
          source_categories text[] NOT NULL,
          tags text[] NOT NULL,
          description text,
          best_for text,
          features text[] NOT NULL,
          attrs jsonb NOT NULL,
          occasion_tags text[] NOT NULL,
          style_tags text[] NOT NULL,
          size_class text,
          rating numeric(2,1),
          review_count int,
          promotion text,
          image_url text,
          product_url text,
          search_text text NOT NULL,
          embedding vector(1024),
          embedding_model text,
          embedded_at timestamptz,
          synthetic_flags text[] NOT NULL,
          is_active boolean NOT NULL,
          source_payload jsonb
        ) ON COMMIT DROP
        """
    )
    cursor.execute(
        """
        CREATE TEMP TABLE stage_variants (
          retailer_id text NOT NULL,
          product_external_id text NOT NULL,
          external_variant_id text,
          sku text,
          colour_raw text,
          colour_family text,
          colour_shade text,
          size_label text,
          size_norm text NOT NULL,
          price numeric(10,2) NOT NULL,
          was_price numeric(10,2),
          in_stock boolean NOT NULL,
          image_url text,
          variant_url text
        ) ON COMMIT DROP
        """
    )


def _merge_products(cursor: Any, retailer_id: str) -> None:
    cursor.execute(
        """
        INSERT INTO products (
          retailer_id, external_id, title, brand, product_line, department, product_type,
          source_categories, tags, description, best_for, features, attrs, occasion_tags,
          style_tags, size_class, rating, review_count, promotion, image_url, product_url,
          search_text, embedding_model, embedded_at, synthetic_flags, is_active, source_payload
        )
        SELECT retailer_id, external_id, title, brand, product_line, department, product_type,
               source_categories, tags, description, best_for, features, attrs, occasion_tags,
               style_tags, size_class, rating, review_count, promotion, image_url, product_url,
               search_text, embedding_model, embedded_at, synthetic_flags, is_active, source_payload
        FROM stage_products
        ON CONFLICT (retailer_id, external_id) DO UPDATE SET
          title = EXCLUDED.title,
          brand = EXCLUDED.brand,
          product_line = EXCLUDED.product_line,
          department = EXCLUDED.department,
          product_type = EXCLUDED.product_type,
          source_categories = EXCLUDED.source_categories,
          tags = EXCLUDED.tags,
          description = EXCLUDED.description,
          best_for = EXCLUDED.best_for,
          features = EXCLUDED.features,
          attrs = EXCLUDED.attrs,
          occasion_tags = EXCLUDED.occasion_tags,
          style_tags = EXCLUDED.style_tags,
          size_class = EXCLUDED.size_class,
          rating = EXCLUDED.rating,
          review_count = EXCLUDED.review_count,
          promotion = EXCLUDED.promotion,
          image_url = EXCLUDED.image_url,
          product_url = EXCLUDED.product_url,
          embedding = CASE
            WHEN products.search_text IS DISTINCT FROM EXCLUDED.search_text THEN NULL
            ELSE products.embedding
          END,
          search_text = EXCLUDED.search_text,
          embedding_model = CASE
            WHEN products.search_text IS DISTINCT FROM EXCLUDED.search_text THEN NULL
            ELSE products.embedding_model
          END,
          embedded_at = CASE
            WHEN products.search_text IS DISTINCT FROM EXCLUDED.search_text THEN NULL
            ELSE products.embedded_at
          END,
          synthetic_flags = EXCLUDED.synthetic_flags,
          is_active = TRUE,
          source_payload = EXCLUDED.source_payload,
          updated_at = now()
        WHERE products.retailer_id = %s
        """,
        (retailer_id,),
    )


def _merge_variants(cursor: Any, retailer_id: str) -> None:
    cursor.execute(
        """
        INSERT INTO variants (
          product_id, retailer_id, external_variant_id, sku, colour_raw, colour_family,
          colour_shade, size_label, size_norm, price, was_price, in_stock, image_url, variant_url
        )
        SELECT p.product_id, s.retailer_id, s.external_variant_id, s.sku, s.colour_raw,
               s.colour_family, s.colour_shade, s.size_label, s.size_norm, s.price,
               s.was_price, s.in_stock, s.image_url, s.variant_url
        FROM stage_variants s
        JOIN products p
          ON p.retailer_id = s.retailer_id AND p.external_id = s.product_external_id
        ON CONFLICT (product_id, (coalesce(colour_raw, '')), size_norm) DO UPDATE SET
          retailer_id = EXCLUDED.retailer_id,
          external_variant_id = EXCLUDED.external_variant_id,
          sku = EXCLUDED.sku,
          colour_family = EXCLUDED.colour_family,
          colour_shade = EXCLUDED.colour_shade,
          size_label = EXCLUDED.size_label,
          price = EXCLUDED.price,
          was_price = EXCLUDED.was_price,
          in_stock = EXCLUDED.in_stock,
          image_url = EXCLUDED.image_url,
          variant_url = EXCLUDED.variant_url
        """
    )
    cursor.execute(
        """
        UPDATE variants v
        SET in_stock = FALSE
        FROM products p
        WHERE p.product_id = v.product_id
          AND p.retailer_id = v.retailer_id
          AND p.retailer_id = %s
          AND NOT EXISTS (
            SELECT 1
            FROM stage_variants s
            WHERE s.retailer_id = p.retailer_id
              AND s.product_external_id = p.external_id
              AND s.colour_raw IS NOT DISTINCT FROM v.colour_raw
              AND s.size_norm = v.size_norm
          )
        """,
        (retailer_id,),
    )
    cursor.execute(
        """
        UPDATE products p
        SET is_active = FALSE, updated_at = now()
        WHERE p.retailer_id = %s
          AND NOT EXISTS (
            SELECT 1 FROM stage_products s
            WHERE s.retailer_id = p.retailer_id AND s.external_id = p.external_id
          )
        """,
        (retailer_id,),
    )


def load_batches(batches: list[RetailerBatch], database_url: str, *, reset: bool = False) -> None:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "The database loader requires psycopg. Install it with "
            "`uv sync --extra database` from the workspace root."
        ) from exc

    with psycopg.connect(database_url, connect_timeout=15) as connection:
        with connection.cursor() as cursor:
            _apply_migrations(cursor, reset)
            _create_staging_tables(cursor)
            for batch in batches:
                _upsert_retailer(cursor, batch)
                cursor.execute("TRUNCATE stage_products, stage_variants")
                _copy_rows(cursor, "stage_products", _PRODUCT_COLUMNS, batch.products)
                _copy_rows(cursor, "stage_variants", _VARIANT_COLUMNS, batch.variants)
                _merge_products(cursor, batch.retailer_id)
                _merge_variants(cursor, batch.retailer_id)
                print(
                    f"Processed {batch.retailer_id}: {len(batch.products):,} products, "
                    f"{len(batch.variants):,} variants"
                )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Synthesize the configured demo catalog data and load both retailers into PostgreSQL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run enrichment and mapping, then print counts without connecting to PostgreSQL.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and rebuild only this loader's managed tables before loading both catalogs.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive action required by --reset.",
    )
    args = parser.parse_args(argv)
    if args.yes and not args.reset:
        parser.error("--yes is only valid with --reset.")
    if args.reset and not args.yes:
        parser.error("--reset drops the managed schema; rerun with --reset --yes to confirm.")

    batches = prepare_all_batches()
    for batch in batches:
        print(
            f"Prepared {batch.retailer_id}: {len(batch.products):,} products, "
            f"{len(batch.variants):,} variants"
        )
    if args.dry_run:
        return 0

    load_database_environment()
    database_url = os.environ.get("DATABASE_URL_UNPOOLED") or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL_UNPOOLED or DATABASE_URL is not set. Configure the connection URL in "
            "backend/.env.local or the process environment; do not commit or paste it into chat."
        )
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise ValueError("DATABASE_URL must be a PostgreSQL connection URL.")

    load_batches(batches, database_url, reset=args.reset)
    print("Schema and catalog load completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
