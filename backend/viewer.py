"""Local, read-only catalog viewer. This module does not load agent or LLM code."""

from __future__ import annotations

import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

from .catalog import Catalog, load_catalog
from retail_agent.config import load_retailer
from retail_agent.models import Product

VIEWER_HTML = Path(__file__).with_name("viewer.html")
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "retailers" / "nordstrom.json"
PAGE_SIZE_DEFAULT = 36
PAGE_SIZE_MAX = 100


def filter_products(
    products: Iterable[Product],
    *,
    query: str = "",
    category: str = "",
    brand: str = "",
    color: str = "",
    size: str = "",
    availability: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[Product]:
    """Apply display filters directly to normalized catalog records."""
    query_terms = query.casefold().split()
    category = category.casefold()
    brand = brand.casefold()
    color = color.casefold()
    size = size.casefold()

    filtered = []
    for product in products:
        if category and product.category.casefold() != category:
            continue
        if brand and brand not in product.brand.casefold():
            continue
        if color and product.color_family.casefold() != color:
            continue
        if size and size not in {value.casefold() for value in product.sizes_in_stock}:
            continue
        if availability == "in_stock" and not product.in_stock:
            continue
        if availability == "out_of_stock" and product.in_stock:
            continue
        if min_price is not None and product.price < min_price:
            continue
        if max_price is not None and product.price > max_price:
            continue
        searchable = " ".join(
            (product.sku, product.name, product.brand, product.category, product.description, *product.tags)
        ).casefold()
        if query_terms and not all(term in searchable for term in query_terms):
            continue
        filtered.append(product)
    return filtered


def _parse_price(value: str, field: str) -> float | None:
    if not value:
        return None
    try:
        price = float(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a number.") from exc
    if not math.isfinite(price) or price < 0:
        raise ValueError(f"{field} must be a finite, non-negative number.")
    return price


def _product_json(product: Product) -> dict:
    return {
        "sku": product.sku,
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "price": product.price,
        "was_price": product.was_price,
        "color_family": product.color_family,
        "color_shade": product.color_shade,
        "sizes_in_stock": product.sizes_in_stock if product.is_sized else (
            ["ONE SIZE"] if product.in_stock else []
        ),
        "in_stock": product.in_stock,
        "stock_is_synthetic": product.stock_is_synthetic,
        "description": product.description[:400],
        "tags": sorted(product.tags),
    }


def _sort_products(products: list[Product], sort: str) -> None:
    if sort == "price_asc":
        products.sort(key=lambda product: (product.price, product.sku))
    elif sort == "price_desc":
        products.sort(key=lambda product: (-product.price, product.sku))
    elif sort == "name":
        products.sort(key=lambda product: (product.name.casefold(), product.sku))
    else:
        raise ValueError("sort must be price_asc, price_desc, or name.")


def make_handler(catalog: Catalog) -> type[BaseHTTPRequestHandler]:
    """Bind the normalized catalog to a small JSON API and static HTML page."""

    class CatalogViewerHandler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: dict, status: int = 200) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(VIEWER_HTML.read_bytes(), "text/html; charset=utf-8")
                return
            if parsed.path not in {"/api/options", "/api/products"}:
                self._send_json({"error": "Not found."}, 404)
                return

            params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if parsed.path == "/api/options":
                self._send_json(
                    {
                        "retailer": catalog.retailer.display_name,
                        "product_count": len(catalog),
                        "categories": sorted({p.category for p in catalog.products if p.category}),
                        "color_families": sorted({p.color_family for p in catalog.products if p.color_family}),
                        "sizes": sorted(
                            {
                                value
                                for system_sizes in catalog.enrichment.size_systems.values()
                                for value in system_sizes
                            }
                        ),
                        "synthetic_stock": any(p.stock_is_synthetic for p in catalog.products),
                    }
                )
                return

            try:
                min_price = _parse_price(params.get("min_price", ""), "min_price")
                max_price = _parse_price(params.get("max_price", ""), "max_price")
                if min_price is not None and max_price is not None and min_price > max_price:
                    raise ValueError("min_price cannot exceed max_price.")
                availability = params.get("availability", "")
                if availability not in {"", "in_stock", "out_of_stock"}:
                    raise ValueError("availability must be in_stock or out_of_stock.")
                page = int(params.get("page", "1"))
                page_size = int(params.get("page_size", str(PAGE_SIZE_DEFAULT)))
                if page < 1:
                    raise ValueError("page must be at least 1.")
                if not 1 <= page_size <= PAGE_SIZE_MAX:
                    raise ValueError(f"page_size must be between 1 and {PAGE_SIZE_MAX}.")
                sort = params.get("sort", "price_asc")
                products = filter_products(
                    catalog.products,
                    query=params.get("q", ""),
                    category=params.get("category", ""),
                    brand=params.get("brand", ""),
                    color=params.get("color", ""),
                    size=params.get("size", ""),
                    availability=availability,
                    min_price=min_price,
                    max_price=max_price,
                )
                _sort_products(products, sort)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, 400)
                return

            total = len(products)
            start = (page - 1) * page_size
            self._send_json(
                {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "products": [_product_json(product) for product in products[start:start + page_size]],
                }
            )

        def log_message(self, format: str, *args) -> None:
            print(f"[catalog-viewer] {self.address_string()} - {format % args}")

    return CatalogViewerHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Retailer config JSON path.")
    parser.add_argument("--port", type=int, default=8765, help="Local port to serve the viewer on.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")

    retailer, enrichment = load_retailer(args.config)
    catalog = load_catalog(retailer, enrichment)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(catalog))
    print(f"Loaded {retailer.display_name}: {len(catalog):,} products.")
    print(f"Catalog viewer: http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping catalog viewer.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
