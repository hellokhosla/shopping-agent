"""Read-only catalog queries for the agent's search nodes (database.md section 11).

A LangGraph node asks the LLM for a `SearchRequest` (structured output), then calls one of these functions:

- `search_catalog`   hybrid search (11.4) plus near misses when there are fewer than 3 exact matches (11.5)
- `exact_search`     hard filters only (11.1)
- `keyword_search`   hard filters plus full-text ranking (11.2)
- `near_miss_search` relaxed price/shade matches, each labelled with why it missed (11.5)
- `carry_on_fit`     luggage size class vs. airline limits (11.6)
- `get_products`     product cards for known IDs
- `catalog_facets`   allowed filter values, to put in the LLM prompt
- `suggest_brands`   typo-tolerant brand lookup

Hard filters (price, colour, size, stock) run on `variants`; ranking runs on `products`. Every query is scoped to
one retailer. Semantic search (11.3) is wired in but optional: pass `query_vector` once embeddings are populated.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from .colors import normalize_color_word
from .database_config import load_database_environment

NEAR_MISS_THRESHOLD = 3
NEAR_MISS_PRICE_TOLERANCE = 0.10
RRF_K = 60
CANDIDATE_POOL = 50
BRAND_SIMILARITY = 0.3
SIZE_CLASSES = ("mini_carry_on", "carry_on", "medium", "large", "set")


class SearchRequest(BaseModel):
    """What the LLM extracts from a shopper message. Every field except `retailer_id` is optional."""

    retailer_id: str = Field(description="Retailer the session belongs to, e.g. 'nordstrom' or 'calpak'.")
    query: str | None = Field(
        default=None,
        description="Free-text words to rank by: product words, materials, styles, e.g. 'satin midi'.",
    )
    product_types: list[str] | None = Field(
        default=None, description="Normalized product types, e.g. ['dress'] or ['carry_on_luggage']."
    )
    department: str | None = Field(default=None, description="e.g. clothing, shoes, bags, accessories, luggage.")
    brand: str | None = Field(default=None, description="Brand as the shopper wrote it; typos are tolerated.")
    colour: str | None = Field(default=None, description="Shopper colour word, e.g. 'navy', 'red', 'beige'.")
    size: str | None = Field(default=None, description="Apparel or shoe size, e.g. 'M' or '8.5'.")
    size_classes: list[str] | None = Field(
        default=None, description="Luggage size classes: mini_carry_on, carry_on, medium, large, set."
    )
    tags: list[str] | None = Field(default=None, description="Retailer tags that must all be present.")
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, gt=0)
    in_stock_only: bool = True
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("size")
    @classmethod
    def _normalize_size(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        size = value.strip().upper()
        if size.endswith(".0"):
            size = size[:-2]
        return size

    @field_validator("size_classes")
    @classmethod
    def _check_size_classes(cls, value: list[str] | None) -> list[str] | None:
        if value and (unknown := set(value) - set(SIZE_CLASSES)):
            raise ValueError(f"unknown size classes: {sorted(unknown)}")
        return value or None

    @field_validator("query", "brand", "colour", "department")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value else None


class ColourFilter(BaseModel):
    word: str
    family: str
    shades: list[str] | None  # None = any shade in the family counts as exact


class VariantHit(BaseModel):
    variant_id: int
    sku: str | None
    colour_raw: str | None
    colour_family: str | None
    colour_shade: str | None
    size: str
    price: float
    was_price: float | None
    in_stock: bool
    image_url: str | None


class ProductHit(BaseModel):
    product_id: int
    retailer_id: str
    title: str
    brand: str | None
    product_type: str
    department: str
    size_class: str | None
    min_price: float
    max_price: float
    rating: float | None
    review_count: int | None
    promotion: str | None
    image_url: str | None
    product_url: str | None
    synthetic_flags: list[str]
    score: float | None = None
    lex_rank: int | None = None
    sem_rank: int | None = None
    is_near_miss: bool = False
    miss_reasons: list[str] = Field(default_factory=list)
    variants: list[VariantHit] = Field(description="Variants that pass the filters, cheapest first.")


class SearchResult(BaseModel):
    request: SearchRequest
    hits: list[ProductHit]
    near_misses: list[ProductHit] = Field(default_factory=list)
    resolved_brand: str | None = None
    colour: ColourFilter | None = None
    notes: list[str] = Field(default_factory=list)


class CarryOnFit(BaseModel):
    product_id: int
    title: str
    size_class: str
    h_in: float
    w_in: float
    d_in: float
    is_typical: bool
    airlines_ok: int
    airlines_total: int


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Read-only connection using DATABASE_URL (process env first, then backend/.env.local)."""
    load_database_environment()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; configure it in backend/.env.local.")
    with psycopg.connect(url, connect_timeout=10, row_factory=dict_row) as conn:
        conn.read_only = True
        yield conn


@contextmanager
def _use(conn: psycopg.Connection | None) -> Iterator[psycopg.Connection]:
    if conn is not None:
        yield conn
    else:
        with connect() as own:
            yield own


def resolve_colour(word: str | None) -> ColourFilter | None:
    """Map a shopper colour word to the stored family and exact shades, using backend/colors.py."""
    if not word:
        return None
    mapped = normalize_color_word(word)
    if mapped is None:
        return None
    family, shades = mapped
    return ColourFilter(word=word, family=family.replace("/", "_"), shades=sorted(shades) if shades else None)


# --- SQL building ---------------------------------------------------------------------------------------------

def _variant_conditions(
    request: SearchRequest, colour: ColourFilter | None, *, relaxed: bool
) -> tuple[list[str], dict[str, Any]]:
    """Conditions on `v`. Relaxed = near-miss tolerances: price +10%, any shade in the family. Size is never relaxed."""
    conds: list[str] = []
    params: dict[str, Any] = {}
    if request.in_stock_only:
        conds.append("v.in_stock")
    if request.max_price is not None:
        factor = 1 + NEAR_MISS_PRICE_TOLERANCE if relaxed else 1
        conds.append("v.price <= %(max_price)s")
        params["max_price"] = round(request.max_price * factor, 2)
    if request.min_price is not None:
        conds.append("v.price >= %(min_price)s")
        params["min_price"] = request.min_price
    if request.size:
        conds.append("v.size_norm IN (%(size)s, 'ONE_SIZE')")
        params["size"] = request.size
    if colour:
        conds.append("v.colour_family = %(colour_family)s")
        params["colour_family"] = colour.family
        if colour.shades and not relaxed:
            conds.append("v.colour_shade = ANY(%(colour_shades)s)")
            params["colour_shades"] = colour.shades
    return conds, params


def _product_conditions(request: SearchRequest, brand: str | None) -> tuple[list[str], dict[str, Any]]:
    conds = ["p.retailer_id = %(retailer_id)s", "p.is_active"]
    params: dict[str, Any] = {"retailer_id": request.retailer_id}
    if request.product_types:
        conds.append("p.product_type = ANY(%(product_types)s)")
        params["product_types"] = request.product_types
    if request.department:
        conds.append("p.department = %(department)s")
        params["department"] = request.department.lower()
    if brand:
        conds.append("lower(p.brand) = lower(%(brand)s)")
        params["brand"] = brand
    if request.size_classes:
        conds.append("p.size_class = ANY(%(size_classes)s)")
        params["size_classes"] = request.size_classes
    if request.tags:
        conds.append("p.tags @> %(tags)s")
        params["tags"] = request.tags
    return conds, params


def _ranked_search(
    conn: psycopg.Connection,
    request: SearchRequest,
    *,
    brand: str | None,
    colour: ColourFilter | None,
    text_mode: Literal["none", "all", "any"],
    require_text_match: bool,
    query_vector: Sequence[float] | None = None,
    relaxed: bool = False,
    exclude_ids: Sequence[int] = (),
) -> list[ProductHit]:
    """Eligible set -> keyword/vector ranks -> RRF (database.md 11.4) -> matching variants per product."""
    v_conds, v_params = _variant_conditions(request, colour, relaxed=relaxed)
    p_conds, p_params = _product_conditions(request, brand)
    params = {**p_params, **v_params, "limit": request.limit, "pool": CANDIDATE_POOL, "rrf_k": RRF_K}
    variant_where = " AND ".join(["v.product_id = p.product_id", "v.retailer_id = p.retailer_id", *v_conds])
    p_conds.append(f"EXISTS (SELECT 1 FROM variants v WHERE {variant_where})")
    if exclude_ids:
        p_conds.append("p.product_id <> ALL(%(exclude_ids)s::bigint[])")
        params["exclude_ids"] = list(exclude_ids)

    use_text = text_mode != "none" and bool(request.query)
    if use_text:
        params["query"] = request.query
        tsquery = (
            "websearch_to_tsquery('english', %(query)s)"
            if text_mode == "all"
            # OR the words together for recall; ts_rank_cd still favours rows matching more of them.
            else "replace(plainto_tsquery('english', %(query)s)::text, ' & ', ' | ')::tsquery"
        )
    use_vector = query_vector is not None
    if use_vector:
        params["qvec"] = "[" + ",".join(str(float(x)) for x in query_vector) + "]"

    ctes = [f"eligible AS (SELECT p.product_id FROM products p WHERE {' AND '.join(p_conds)})"]
    if use_text:
        # A query with no searchable words (only stop words) ranks nothing but doesn't filter anything out either.
        match = "(numnode(q) = 0 OR p.search_tsv @@ q)"
        ctes.append(
            f"""lex AS (
              SELECT p.product_id, row_number() OVER (
                       ORDER BY ts_rank_cd(p.search_tsv, q) DESC, p.rating DESC NULLS LAST, p.product_id) AS r
              FROM products p JOIN eligible USING (product_id), (SELECT {tsquery} AS q) AS tq
              WHERE {match}
              ORDER BY r LIMIT %(pool)s)"""
        )
    if use_vector:
        ctes.append(
            """sem AS (
              SELECT p.product_id, row_number() OVER (ORDER BY p.embedding <=> %(qvec)s::vector) AS r
              FROM products p JOIN eligible USING (product_id)
              WHERE p.embedding IS NOT NULL
              ORDER BY r LIMIT %(pool)s)"""
        )

    if use_text and use_vector:
        join_ranks = "lex FULL OUTER JOIN sem USING (product_id)"
        rank_cols = "lex.r AS lex_rank, sem.r AS sem_rank, coalesce(lex.r, sem.r) AS ord"
        score = "coalesce(1.0 / (%(rrf_k)s + lex.r), 0) + coalesce(1.0 / (%(rrf_k)s + sem.r), 0)"
        if require_text_match:
            join_ranks = "lex LEFT JOIN sem USING (product_id)"
    elif use_text:
        join_ranks, rank_cols, score = "lex", "lex.r AS lex_rank, NULL::bigint AS sem_rank, lex.r AS ord", "1.0 / (%(rrf_k)s + lex.r)"
    elif use_vector:
        join_ranks, rank_cols, score = "sem", "NULL::bigint AS lex_rank, sem.r AS sem_rank, sem.r AS ord", "1.0 / (%(rrf_k)s + sem.r)"
    else:
        ctes.append(
            """popular AS (
              SELECT p.product_id, row_number() OVER (
                       ORDER BY p.rating DESC NULLS LAST, p.review_count DESC NULLS LAST, p.product_id) AS r
              FROM products p JOIN eligible USING (product_id)
              ORDER BY r LIMIT %(pool)s)"""
        )
        join_ranks, rank_cols, score = "popular", "NULL::bigint AS lex_rank, NULL::bigint AS sem_rank, popular.r AS ord", "NULL::float8"

    if use_text and not require_text_match and not use_vector:
        # Hybrid without vectors: products with no keyword hit still qualify, ranked after the keyword hits.
        ctes.append(
            """fill AS (
              SELECT p.product_id, row_number() OVER (
                       ORDER BY p.rating DESC NULLS LAST, p.review_count DESC NULLS LAST, p.product_id) AS r
              FROM products p JOIN eligible USING (product_id)
              WHERE p.product_id NOT IN (SELECT product_id FROM lex)
              ORDER BY r LIMIT %(limit)s)"""
        )
        ranked = f"""
          SELECT product_id, {score}::float8 AS score, {rank_cols} FROM {join_ranks}
          UNION ALL
          SELECT product_id, 0::float8, NULL::bigint, NULL::bigint, r FROM fill"""
    else:
        ranked = f"SELECT product_id, {score}::float8 AS score, {rank_cols} FROM {join_ranks}"

    sql = f"""
    WITH {', '.join(ctes)},
    ranked AS (
      SELECT *, row_number() OVER (ORDER BY score DESC NULLS LAST, ord) AS pos FROM ({ranked}) AS r
      ORDER BY pos LIMIT %(limit)s
    )
    SELECT r.score, r.lex_rank, r.sem_rank,
           p.product_id, p.retailer_id, p.title, p.brand, p.product_type, p.department, p.size_class,
           p.rating, p.review_count, p.promotion, p.image_url, p.product_url, p.synthetic_flags,
           m.variants
    FROM ranked r
    JOIN products p USING (product_id)
    CROSS JOIN LATERAL (
      SELECT jsonb_agg(jsonb_build_object(
               'variant_id', v.variant_id, 'sku', v.sku, 'colour_raw', v.colour_raw,
               'colour_family', v.colour_family, 'colour_shade', v.colour_shade, 'size', v.size_norm,
               'price', v.price, 'was_price', v.was_price, 'in_stock', v.in_stock, 'image_url', v.image_url
             ) ORDER BY v.price, v.variant_id) AS variants
      FROM variants v WHERE {variant_where}
    ) m
    ORDER BY r.pos
    """
    rows = conn.execute(sql, params).fetchall()
    return [_to_hit(row) for row in rows]


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (Decimal, int, float)) else None


def _to_hit(row: dict[str, Any]) -> ProductHit:
    variants = [VariantHit(**v) for v in row["variants"] or []]
    prices = [v.price for v in variants]
    return ProductHit(
        product_id=row["product_id"],
        retailer_id=row["retailer_id"],
        title=row["title"],
        brand=row["brand"],
        product_type=row["product_type"],
        department=row["department"],
        size_class=row["size_class"],
        min_price=min(prices) if prices else 0.0,
        max_price=max(prices) if prices else 0.0,
        rating=_num(row["rating"]),
        review_count=row["review_count"],
        promotion=row["promotion"],
        image_url=row["image_url"],
        product_url=row["product_url"],
        synthetic_flags=list(row["synthetic_flags"] or []),
        score=_num(row["score"]),
        lex_rank=row["lex_rank"],
        sem_rank=row["sem_rank"],
        variants=variants,
    )


def miss_reasons(variant: VariantHit, request: SearchRequest, colour: ColourFilter | None) -> list[str]:
    """Why a variant is a near miss rather than an exact match (empty = exact)."""
    reasons = []
    if request.max_price is not None and variant.price > request.max_price:
        reasons.append(f"${math.ceil(variant.price - request.max_price)} over your budget")
    if colour and colour.shades and variant.colour_shade not in colour.shades:
        reasons.append(f"{variant.colour_shade or 'shade not confirmed'}, not {colour.word}")
    return reasons


def _label_near_misses(
    hits: list[ProductHit], request: SearchRequest, colour: ColourFilter | None
) -> list[ProductHit]:
    labelled = []
    for hit in hits:
        scored = sorted(
            ((miss_reasons(v, request, colour), v) for v in hit.variants),
            key=lambda pair: (len(pair[0]), pair[1].price),
        )
        if not scored or not scored[0][0]:
            continue  # an exact variant exists; it isn't a near miss
        best_reasons = scored[0][0]
        hit.variants = [v for reasons, v in scored if len(reasons) == len(best_reasons)]
        hit.is_near_miss = True
        hit.miss_reasons = best_reasons
        labelled.append(hit)
    return labelled


# --- Public functions -----------------------------------------------------------------------------------------

def suggest_brands(
    retailer_id: str, text: str, *, limit: int = 5, conn: psycopg.Connection | None = None
) -> list[tuple[str, float]]:
    """Closest brand names by trigram similarity, e.g. 'calpack' -> [('CALPAK', 0.54)]."""
    with _use(conn) as c:
        rows = c.execute(
            """
            SELECT brand, similarity(brand, %(text)s) AS sim
            FROM (SELECT DISTINCT brand FROM products
                  WHERE retailer_id = %(retailer_id)s AND is_active AND brand IS NOT NULL) b
            WHERE similarity(brand, %(text)s) >= %(threshold)s
            ORDER BY sim DESC, brand LIMIT %(limit)s
            """,
            {"retailer_id": retailer_id, "text": text, "threshold": BRAND_SIMILARITY, "limit": limit},
        ).fetchall()
    return [(r["brand"], round(float(r["sim"]), 3)) for r in rows]


def resolve_brand(retailer_id: str, text: str, *, conn: psycopg.Connection | None = None) -> str | None:
    """Exact brand (case-insensitive) if it exists, else the closest trigram match, else None."""
    with _use(conn) as c:
        row = c.execute(
            "SELECT brand FROM products WHERE retailer_id = %s AND is_active AND lower(brand) = lower(%s) LIMIT 1",
            (retailer_id, text),
        ).fetchone()
        if row:
            return row["brand"]
        suggestions = suggest_brands(retailer_id, text, limit=1, conn=c)
    return suggestions[0][0] if suggestions else None


def _prepare(
    request: SearchRequest, conn: psycopg.Connection
) -> tuple[str | None, ColourFilter | None, list[str], bool]:
    """Resolve brand and colour words. Returns (brand, colour, notes, impossible)."""
    notes: list[str] = []
    brand = None
    if request.brand:
        brand = resolve_brand(request.retailer_id, request.brand, conn=conn)
        if brand is None:
            notes.append(f"No brand like {request.brand!r} at this retailer.")
            return None, None, notes, True
        if brand.lower() != request.brand.lower():
            notes.append(f"Brand {request.brand!r} read as {brand!r}.")
    colour = resolve_colour(request.colour)
    if request.colour and colour is None:
        notes.append(f"Colour {request.colour!r} is not in the colour vocabulary; colour filter ignored.")
    return brand, colour, notes, False


def exact_search(request: SearchRequest, *, conn: psycopg.Connection | None = None) -> SearchResult:
    """Hard filters only (11.1): type, brand, colour, size, price, stock. Ignores `query`. Best rated first."""
    with _use(conn) as c:
        brand, colour, notes, impossible = _prepare(request, c)
        hits = [] if impossible else _ranked_search(
            c, request, brand=brand, colour=colour, text_mode="none", require_text_match=False
        )
    return SearchResult(request=request, hits=hits, resolved_brand=brand, colour=colour, notes=notes)


def keyword_search(
    request: SearchRequest,
    *,
    match: Literal["all", "any"] = "all",
    conn: psycopg.Connection | None = None,
) -> SearchResult:
    """Full-text search (11.2) within the hard filters. `match='all'` needs every word; 'any' needs one."""
    if not request.query:
        raise ValueError("keyword_search needs request.query")
    with _use(conn) as c:
        brand, colour, notes, impossible = _prepare(request, c)
        hits = [] if impossible else _ranked_search(
            c, request, brand=brand, colour=colour, text_mode=match, require_text_match=True
        )
    return SearchResult(request=request, hits=hits, resolved_brand=brand, colour=colour, notes=notes)


def near_miss_search(
    request: SearchRequest,
    *,
    exclude_ids: Sequence[int] = (),
    query_vector: Sequence[float] | None = None,
    conn: psycopg.Connection | None = None,
) -> list[ProductHit]:
    """Relaxed matches (11.5): price up to +10% and other shades of the same colour family. Size is never relaxed.

    Each hit carries `miss_reasons`, e.g. ['$4 over your budget', 'burgundy, not red'].
    """
    with _use(conn) as c:
        brand, colour, _, impossible = _prepare(request, c)
        if impossible:
            return []
        hits = _ranked_search(
            c, request, brand=brand, colour=colour, text_mode="any", require_text_match=False,
            query_vector=query_vector, relaxed=True, exclude_ids=exclude_ids,
        )
    return _label_near_misses(hits, request, colour)


def search_catalog(
    request: SearchRequest,
    *,
    query_vector: Sequence[float] | None = None,
    conn: psycopg.Connection | None = None,
) -> SearchResult:
    """Main entry point for the search node (11.4 + 11.5).

    Hard filters pick the eligible products; `query` words rank them (keyword hits first, then the rest by
    rating). Pass `query_vector` (embedding of the shopper's text, same model as `products.embedding`) to add
    semantic ranking, fused with keyword ranks by RRF. With fewer than 3 hits, near misses are added.
    """
    with _use(conn) as c:
        brand, colour, notes, impossible = _prepare(request, c)
        if impossible:
            return SearchResult(request=request, hits=[], notes=notes)
        hits = _ranked_search(
            c, request, brand=brand, colour=colour, text_mode="any", require_text_match=False,
            query_vector=query_vector,
        )
        near: list[ProductHit] = []
        can_relax = request.max_price is not None or (colour is not None and colour.shades)
        if len(hits) < NEAR_MISS_THRESHOLD and can_relax:
            near = near_miss_search(
                request, exclude_ids=[h.product_id for h in hits], query_vector=query_vector, conn=c
            )
            near = near[: max(request.limit - len(hits), 0)]
    return SearchResult(
        request=request, hits=hits, near_misses=near, resolved_brand=brand, colour=colour, notes=notes
    )


def get_products(
    retailer_id: str,
    product_ids: Sequence[int],
    *,
    in_stock_only: bool = False,
    conn: psycopg.Connection | None = None,
) -> list[ProductHit]:
    """Product cards with all their variants, in the order given. IDs from another retailer are ignored."""
    if not product_ids:
        return []
    stock = "AND v.in_stock" if in_stock_only else ""
    with _use(conn) as c:
        rows = c.execute(
            f"""
            SELECT NULL::float8 AS score, NULL::bigint AS lex_rank, NULL::bigint AS sem_rank,
                   p.product_id, p.retailer_id, p.title, p.brand, p.product_type, p.department, p.size_class,
                   p.rating, p.review_count, p.promotion, p.image_url, p.product_url, p.synthetic_flags,
                   (SELECT jsonb_agg(jsonb_build_object(
                             'variant_id', v.variant_id, 'sku', v.sku, 'colour_raw', v.colour_raw,
                             'colour_family', v.colour_family, 'colour_shade', v.colour_shade,
                             'size', v.size_norm, 'price', v.price, 'was_price', v.was_price,
                             'in_stock', v.in_stock, 'image_url', v.image_url
                           ) ORDER BY v.price, v.variant_id)
                    FROM variants v
                    WHERE v.product_id = p.product_id AND v.retailer_id = p.retailer_id {stock}) AS variants
            FROM products p
            WHERE p.retailer_id = %(retailer_id)s AND p.product_id = ANY(%(ids)s::bigint[])
            ORDER BY array_position(%(ids)s::bigint[], p.product_id)
            """,
            {"retailer_id": retailer_id, "ids": list(product_ids)},
        ).fetchall()
    return [_to_hit(row) for row in rows]


def carry_on_fit(
    retailer_id: str = "calpak",
    *,
    airline: str | None = None,
    conn: psycopg.Connection | None = None,
) -> list[CarryOnFit]:
    """Carry-on fit (11.6): typical size-class dimensions vs. airline carry-on limits.

    Returns nothing until `size_class_dims` and `airline_limits` are seeded. Dimensions are typical, never a
    guarantee (`is_typical`).
    """
    with _use(conn) as c:
        rows = c.execute(
            """
            SELECT p.product_id, p.title, p.size_class, d.h_in, d.w_in, d.d_in, d.is_typical,
                   count(*) FILTER (WHERE a.fits) AS airlines_ok, count(*) AS airlines_total
            FROM products p
            JOIN size_class_dims d ON d.retailer_id = p.retailer_id AND d.size_class = p.size_class
            CROSS JOIN LATERAL (
              SELECT (d.h_in <= al.max_h_in AND d.w_in <= al.max_w_in AND d.d_in <= al.max_d_in) AS fits
              FROM airline_limits al
              WHERE al.bag_type = 'carry_on' AND (%(airline)s::text IS NULL OR al.airline ILIKE %(airline)s)
            ) a
            WHERE p.retailer_id = %(retailer_id)s AND p.is_active
              AND p.size_class IN ('mini_carry_on', 'carry_on')
            GROUP BY p.product_id, p.title, p.size_class, d.h_in, d.w_in, d.d_in, d.is_typical
            ORDER BY p.title
            """,
            {"retailer_id": retailer_id, "airline": airline},
        ).fetchall()
    return [
        CarryOnFit(**{k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}) for row in rows
    ]


def catalog_facets(retailer_id: str, *, conn: psycopg.Connection | None = None) -> dict[str, list[str]]:
    """Allowed filter values for one retailer, for the LLM prompt or for validating its output."""
    with _use(conn) as c:
        def values(sql: str) -> list[str]:
            return [r["value"] for r in c.execute(sql, {"r": retailer_id}).fetchall()]

        return {
            "product_types": values(
                "SELECT DISTINCT product_type AS value FROM products "
                "WHERE retailer_id = %(r)s AND is_active ORDER BY 1"
            ),
            "departments": values(
                "SELECT DISTINCT department AS value FROM products "
                "WHERE retailer_id = %(r)s AND is_active ORDER BY 1"
            ),
            "size_classes": values(
                "SELECT DISTINCT size_class AS value FROM products "
                "WHERE retailer_id = %(r)s AND size_class IS NOT NULL ORDER BY 1"
            ),
            "sizes": values(
                "SELECT DISTINCT size_norm AS value FROM variants WHERE retailer_id = %(r)s ORDER BY 1"
            ),
            "colour_families": values(
                "SELECT DISTINCT colour_family AS value FROM variants "
                "WHERE retailer_id = %(r)s AND colour_family IS NOT NULL ORDER BY 1"
            ),
        }
