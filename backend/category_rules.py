"""Deterministic category eligibility rules for normalized catalog records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .models import Product


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
