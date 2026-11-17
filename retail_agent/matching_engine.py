"""Deterministic Matching & Ranking Engine (PRD "Matching rules" 1-5, M6).

Pure code, no LLM. Given validated constraints it decides which products are
eligible, labels near misses, applies merchandising boosts and ranks results.

Rules (platform-locked, not retailer-configurable):
  1. Exact matches first: price, size, colour family/shade, category, brand and
     stock are all met.
  2. Near misses only when exact matches are fewer than MIN_EXACT_MATCHES.
     Tolerances: price up to PRICE_TOLERANCE over budget; colour in an adjacent
     shade of the same family. Size, stock, category and brand are never relaxed.
  3. Every near miss is labelled with what it misses ("$12 over your budget").
  4. Boosts reorder exact matches only, are labelled "Boosted", and never make
     an item eligible.
  5. The budget check uses the current online price (Product.price).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .config import BoostRule
from .models import MatchResult, Product, RankedProduct, SearchConstraints

MIN_EXACT_MATCHES = 3
PRICE_TOLERANCE = 0.10
DEFAULT_TOP_K = 3
RATING_PRIOR_MEAN = 4.0
RATING_PRIOR_WEIGHT = 10
UNRATED_SCORE = 3.0

BOOSTED_LABEL = "Boosted"
SIZE_NOT_CONFIRMED_LABEL = "size not confirmed"


def money(amount: float) -> str:
    return f"${amount:,.0f}" if abs(amount - round(amount)) < 0.005 else f"${amount:,.2f}"


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in keywords)


def _contains_semantic_term(text: str, term: str) -> bool:
    words = term.lower().split()
    if not words:
        return False
    last = words[-1]
    if last.endswith("ss"):
        words[-1] = last + r"(?:es)?"
    elif last.endswith("s"):
        words[-1] = last[:-1] + r"s?"
    else:
        words[-1] = last + r"s?"
    pattern = r"\b" + r"\s+".join(re.escape(word) if not word.endswith(("?", ")")) else word for word in words) + r"\b"
    return re.search(pattern, text) is not None


@dataclass(frozen=True)
class CategoryRule:
    """A canonical category resolved to one retailer's tags plus name keywords."""

    tags: frozenset[str]
    name_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    item_keywords: tuple[str, ...] = ()
    semantic_terms: tuple[str, ...] = ()

    def matches(self, product: Product) -> bool:
        if not (product.tags & self.tags):
            return False
        name = product.name.lower()
        if self.item_keywords and not _contains_any(name, self.item_keywords):
            return False
        semantic_text = f"{name} {product.description.lower()}"
        if self.semantic_terms and not any(
            _contains_semantic_term(semantic_text, term) for term in self.semantic_terms
        ):
            return False
        if self.name_keywords and not _contains_any(name, self.name_keywords):
            return False
        return not (self.exclude_keywords and _contains_any(name, self.exclude_keywords))


@dataclass(frozen=True)
class Miss:
    attribute: str
    label: str
    severity: float  # 0..1, used to order near misses


@dataclass
class Evaluation:
    eligible: bool
    reject_reason: str | None = None
    misses: list[Miss] = field(default_factory=list)

    @property
    def is_exact(self) -> bool:
        return self.eligible and not self.misses


def evaluate_product(
    product: Product, constraints: SearchConstraints, category_rule: CategoryRule | None
) -> Evaluation:
    """Check one product against every hard limit. Returns exact, near miss or reject."""
    # Never relaxed: category, brand, stock, size, minimum price.
    if category_rule is not None and not category_rule.matches(product):
        return Evaluation(False, "category")
    if constraints.brand and product.brand.lower() != constraints.brand.lower():
        return Evaluation(False, "brand")
    if not product.in_stock:
        return Evaluation(False, "out_of_stock")

    requested_size = constraints.sizes.get(product.size_system) if product.is_sized else None
    if requested_size and requested_size not in product.sizes_in_stock:
        return Evaluation(False, "size")
    if constraints.min_price is not None and product.price < constraints.min_price:
        return Evaluation(False, "below_min_price")

    misses: list[Miss] = []

    if constraints.max_price is not None and product.price > constraints.max_price:
        ceiling = constraints.max_price * (1 + PRICE_TOLERANCE)
        if product.price > ceiling + 1e-9:
            return Evaluation(False, "price")
        over = product.price - constraints.max_price
        misses.append(Miss("price", f"{money(over)} over your budget", over / constraints.max_price))

    if constraints.color_family:
        if product.color_family != constraints.color_family:
            return Evaluation(False, "color")
        shades = constraints.color_shades
        if shades is not None and product.color_shade not in shades:
            # Same family, adjacent shade (e.g. burgundy for red): tolerated, labelled.
            misses.append(Miss("color", f"{product.color_shade}, not {constraints.color_label}", 0.5))

    return Evaluation(True, None, misses)


def boost_strength(product: Product, boosts: Sequence[BoostRule]) -> int:
    strength = 0
    for rule in boosts:
        if (rule.sku and rule.sku == product.sku) or (rule.brand and rule.brand.lower() == product.brand.lower()):
            strength = max(strength, rule.strength)
    return strength


def rating_score(product: Product) -> float:
    """Bayesian-smoothed rating so 5.0 from 2 reviews doesn't beat 4.6 from 900."""
    if product.rating is None or product.review_count <= 0:
        return UNRATED_SCORE
    n = product.review_count
    return (product.rating * n + RATING_PRIOR_MEAN * RATING_PRIOR_WEIGHT) / (n + RATING_PRIOR_WEIGHT)


def relevance_score(product: Product, keywords: Sequence[str]) -> int:
    name = product.name.lower()
    return sum(1 for k in dict.fromkeys(kw.lower() for kw in keywords) if _contains_any(name, [k]))


def match_products(
    products: Iterable[Product],
    constraints: SearchConstraints,
    category_rule: CategoryRule | None = None,
    boosts: Sequence[BoostRule] = (),
    top_k: int = DEFAULT_TOP_K,
    ranking_keywords: Sequence[str] | None = None,
    allow_near_misses: bool = True,
) -> MatchResult:
    """Filter, label and rank products. Deterministic for identical inputs.

    Args:
        products: Candidate products (may be pre-filtered; every rule is re-checked).
        constraints: Validated shopper limits from the intent step.
        category_rule: Resolved category; None means any category.
        boosts: Retailer merchandising rules. Applied to exact matches only.
        top_k: Number of items to return.
        ranking_keywords: Soft preferences extracted from the shopper's request; order only.
        allow_near_misses: Outfit slots set False to use exact matches only.
    """
    keywords = list(ranking_keywords if ranking_keywords is not None else constraints.style_keywords)
    rejected: Counter[str] = Counter()
    exact: list[RankedProduct] = []
    near: list[tuple[tuple, RankedProduct]] = []
    seen: set[str] = set()

    for product in products:
        if product.sku in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(product.sku)

        evaluation = evaluate_product(product, constraints, category_rule)
        if not evaluation.eligible:
            rejected[evaluation.reject_reason or "unknown"] += 1
            continue

        relevance = relevance_score(product, keywords)
        quality = rating_score(product)
        labels: list[str] = []
        if product.size_system in {"apparel", "shoes"} and not constraints.sizes.get(product.size_system):
            labels.append(SIZE_NOT_CONFIRMED_LABEL)

        if evaluation.is_exact:
            strength = boost_strength(product, boosts)
            if strength:
                labels.insert(0, BOOSTED_LABEL)
            score = strength * 100 + relevance * 10 + quality
            exact.append(RankedProduct(product, "exact", labels, boosted=bool(strength), score=score))
        else:
            # Near misses are never boosted (rule 4).
            labels = [m.label for m in evaluation.misses] + labels
            sort_key = (
                len(evaluation.misses),
                sum(m.severity for m in evaluation.misses),
                -relevance,
                -quality,
                product.price,
                product.sku,
            )
            near.append((sort_key, RankedProduct(product, "near_miss", labels, boosted=False, score=relevance * 10 + quality)))

    exact.sort(key=lambda r: (-r.score, r.product.price, r.product.sku))
    near.sort(key=lambda pair: pair[0])

    items = exact[:top_k]
    notes: list[str] = []
    if allow_near_misses and len(exact) < MIN_EXACT_MATCHES and len(items) < top_k:
        fill = [r for _, r in near][: top_k - len(items)]
        items.extend(fill)
        if fill:
            notes.append(
                f"Only {len(exact)} exact match(es); added {len(fill)} labelled near miss(es) "
                f"(price ≤ +{int(PRICE_TOLERANCE * 100)}% or adjacent shade; size never relaxed)."
            )
    if not items:
        notes.append("No products meet the limits, even within near-miss tolerances.")

    return MatchResult(
        items=items,
        exact_count=len(exact),
        near_miss_count=len(near),
        rejected=dict(rejected),
        notes=notes,
    )
