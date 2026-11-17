"""Three-layer configuration: platform code, category packs, retailer config.

Retailers differ only through these files (PRD M1). Platform-locked rules
(boost eligibility, near-miss tolerances, guardrails) live in code, not here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DataEnrichmentConfig(BaseModel):
    size_systems: dict[str, list[str]]


class LLMConfig(BaseModel):
    model: str = "gpt-4.1-mini"
    temperature: float = 0.0


class CatalogSource(BaseModel):
    path: str
    field_mapping: dict[str, str]
    brand_override: str | None = None
    tag_separator: str | None = None
    stock_mode: Literal["synthetic", "source_availability"] = "synthetic"
    drop_categories: list[str] = Field(default_factory=list)
    drop_skus_with_tags: list[str] = Field(default_factory=list)
    max_valid_price: float = 10_000
    color_lookup: str
    size_system_by_category: dict[str, str] = Field(default_factory=dict)
    size_value_by_category: dict[str, str] = Field(default_factory=dict)
    stock_seed: int = 42
    in_stock_rate: float = Field(default=0.8, ge=0, le=1)


class BoostRule(BaseModel):
    brand: str | None = None
    sku: str | None = None
    strength: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _needs_target(self) -> "BoostRule":
        if not self.brand and not self.sku:
            raise ValueError("A boost rule needs a brand or a sku")
        return self


class Merchandising(BaseModel):
    boosts: list[BoostRule] = Field(default_factory=list)


class GuardrailConfig(BaseModel):
    help_page_url: str
    catalog_scope: str
    competitors: list[str] = Field(default_factory=list)
    out_of_catalog_terms: list[str] = Field(default_factory=list)


class RetailerConfig(BaseModel):
    retailer_id: str
    display_name: str
    category_pack: str
    brand_voice: str = "Friendly and concise."
    llm: LLMConfig = Field(default_factory=LLMConfig)
    catalog: CatalogSource
    category_tags: dict[str, list[str]]
    merchandising: Merchandising = Field(default_factory=Merchandising)
    guardrails: GuardrailConfig
    config_dir: Path = Field(default=Path("."), exclude=True)

    @property
    def catalog_path(self) -> Path:
        return (self.config_dir / self.catalog.path).resolve()


def load_retailer(config_path: str | Path) -> tuple[RetailerConfig, DataEnrichmentConfig]:
    """Load a retailer config plus its data-enrichment settings."""
    config_path = Path(config_path).resolve()
    retailer = RetailerConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
    retailer.config_dir = config_path.parent

    pack_path = config_path.parent.parent / "category_packs" / f"{retailer.category_pack}.json"
    enrichment = DataEnrichmentConfig.model_validate_json(pack_path.read_text(encoding="utf-8"))
    unknown_systems = set(retailer.catalog.size_system_by_category.values()) - set(enrichment.size_systems)
    if unknown_systems:
        raise ValueError(f"Catalog maps to undefined size systems: {sorted(unknown_systems)}")
    if retailer.catalog.stock_mode == "source_availability" and "available" not in retailer.catalog.field_mapping:
        raise ValueError("A source_availability catalog must map the 'available' field.")
    for category, size_value in retailer.catalog.size_value_by_category.items():
        system = retailer.catalog.size_system_by_category.get(category, "one_size")
        if size_value not in enrichment.size_systems.get(system, []):
            raise ValueError(f"Size value '{size_value}' for '{category}' is not in size system '{system}'.")
    if retailer.catalog.stock_mode == "source_availability":
        missing_sizes = {
            category
            for category, system in retailer.catalog.size_system_by_category.items()
            if system != "one_size" and category not in retailer.catalog.size_value_by_category
        }
        if missing_sizes:
            raise ValueError(f"Source-available sized categories need size values: {sorted(missing_sizes)}")
    return retailer, enrichment
