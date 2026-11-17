"""Normalized catalog records shared by data consumers."""

from dataclasses import dataclass

ONE_SIZE = "ONE SIZE"


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
    # Per-size stock may be source-backed or synthetic.
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
