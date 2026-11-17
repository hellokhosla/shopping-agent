"""Shared data structures: products, structured intent and match results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

ONE_SIZE = "ONE SIZE"
RequestType = Literal["product_search", "outfit", "compare", "off_topic"]


@dataclass(frozen=True)
class Product:
    """One catalog item in the platform's standard format (PRD M2/M3)."""

    sku: str
    name: str
    brand: str
    price: float
    category: str
    tags: frozenset[str]
    color_code: str
    color_family: str
    color_shade: str
    size_system: str
    # Per-size stock marker (size, quantity); quantity may be source-backed or synthetic.
    stock: tuple[tuple[str, int], ...]
    description: str = ""
    stock_is_synthetic: bool = True
    was_price: float | None = None
    promotion: str | None = None
    rating: float | None = None
    review_count: int = 0

    @property
    def sizes_in_stock(self) -> list[str]:
        return [size for size, qty in self.stock if qty > 0]

    @property
    def in_stock(self) -> bool:
        return any(qty > 0 for _, qty in self.stock)

    @property
    def is_sized(self) -> bool:
        return self.size_system != "one_size"


class OutfitSlotIntent(BaseModel):
    """LLM-proposed outfit slot; code validates its catalog category and budget share."""

    category: str = Field(description="Canonical category key from the retailer's catalog categories.")
    budget_share: float = Field(gt=0, le=1, description="Fraction of the total outfit budget assigned to this slot.")
    apply_color: bool = Field(default=False, description="Whether the shopper's requested color is a hard limit for this slot.")
    match_terms: list[str] = Field(
        default_factory=list,
        description="LLM-inferred title or description phrases that distinguish this item type, not stored category keywords.",
    )


class ShoppingIntent(BaseModel):
    """Structured output the Intent Parser LLM must return. Code validates it."""

    request_type: RequestType = Field(
        description="product_search, outfit, compare (options already shown) or off_topic."
    )
    category: str | None = Field(default=None, description="Canonical category key from the allowed list, or null.")
    category_terms: list[str] = Field(
        default_factory=list,
        description="LLM-inferred phrases for semantically matching the requested item type in product titles or descriptions.",
    )
    max_price: float | None = Field(default=None, description="Upper budget in USD, number only.")
    min_price: float | None = Field(default=None, description="Lower price bound in USD, number only.")
    apparel_size: str | None = Field(default=None, description="Clothing size from the allowed list.")
    shoe_size: str | None = Field(default=None, description="Numeric shoe size as text, e.g. '8' or '8.5'.")
    luggage_size: str | None = Field(
        default=None, description="CALPAK luggage size from the allowed list, such as carry-on/cabin or check-in."
    )
    color: str | None = Field(default=None, description="Shopper's colour word, lowercase.")
    brand: str | None = Field(default=None, description="Brand only if explicitly named.")
    occasion: str | None = Field(default=None, description="Free-form occasion inferred from the request.")
    style_keywords: list[str] = Field(default_factory=list, description="Up to 5 product-name keywords.")
    outfit_slots: list[OutfitSlotIntent] = Field(
        default_factory=list,
        description="For outfit requests, propose item categories and budget shares summing to 1.",
    )
    ask_color: bool | None = Field(
        default=None,
        description="For outfit requests, whether asking for a preferred color would materially help.",
    )
    compare_options: list[int] = Field(default_factory=list, description="Option numbers to compare, if named.")
    assumptions: list[str] = Field(default_factory=list, description="Short notes on interpretations made.")


@dataclass
class SearchConstraints:
    """Validated hard limits (enforced) and soft preferences (ranking only)."""

    category: str | None = None
    category_terms: list[str] = field(default_factory=list)
    max_price: float | None = None
    min_price: float | None = None
    sizes: dict[str, str] = field(default_factory=dict)  # size_system -> size
    color_label: str | None = None
    color_family: str | None = None
    color_shades: frozenset[str] | None = None  # None = any shade in the family
    brand: str | None = None
    occasion: str | None = None
    style_keywords: list[str] = field(default_factory=list)
    outfit_slots: list[OutfitSlotIntent] = field(default_factory=list)
    ask_color: bool = False


@dataclass
class RankedProduct:
    product: Product
    match_type: Literal["exact", "near_miss"]
    labels: list[str]
    boosted: bool = False
    score: float = 0.0


@dataclass
class MatchResult:
    items: list[RankedProduct]
    exact_count: int
    near_miss_count: int
    rejected: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Outfit:
    items: dict[str, RankedProduct]  # slot -> product
    total: float
    missing_slots: list[str] = field(default_factory=list)


@dataclass
class OutfitResult:
    outfits: list[Outfit]
    alternatives: dict[str, list[RankedProduct]]
    budget: float
    notes: list[str] = field(default_factory=list)
