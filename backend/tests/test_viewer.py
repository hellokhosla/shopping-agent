import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from backend.catalog import Catalog
from backend.viewer import filter_products, make_handler
from retail_agent.config import load_retailer
from retail_agent.models import Product

BACKEND = Path(__file__).resolve().parents[1]
CALPAK_CONFIG = BACKEND / "config" / "retailers" / "calpak.json"


def viewer_product(
    sku: str,
    *,
    category: str,
    price: float,
    size: str,
    available: bool = True,
    description: str = "",
) -> Product:
    return Product(
        sku=sku,
        name=f"Travel bag {sku}",
        brand="CALPAK",
        price=price,
        category=category,
        tags=frozenset({category, "Travel"}),
        color_code="BLACK",
        color_family="black/grey",
        color_shade="black",
        size_system="luggage" if size != "ONE SIZE" else "one_size",
        stock=((size, int(available)),),
        description=description,
        stock_is_synthetic=False,
    )


class CatalogViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retailer, cls.enrichment = load_retailer(CALPAK_CONFIG)
        cls.products = [
            viewer_product(
                "carry-on",
                category="Carry-On Luggage",
                price=120,
                size="carry-on/cabin",
                description="Padded laptop sleeve and compression straps.",
            ),
            viewer_product(
                "sold-out",
                category="Carry-On Luggage",
                price=90,
                size="carry-on/cabin",
                available=False,
            ),
            viewer_product("backpack", category="Backpack", price=80, size="ONE SIZE"),
        ]

    def test_filter_products_combines_data_filters(self):
        found = filter_products(
            self.products,
            query="laptop sleeve",
            category="Carry-On Luggage",
            brand="calpak",
            color="black/grey",
            size="carry-on/cabin",
            availability="in_stock",
            min_price=100,
            max_price=150,
        )
        self.assertEqual([product.sku for product in found], ["carry-on"])

    def test_filter_products_can_show_unavailable_items(self):
        found = filter_products(self.products, availability="out_of_stock")
        self.assertEqual([product.sku for product in found], ["sold-out"])

    def test_local_http_viewer_serves_html_options_and_paginated_results(self):
        catalog = Catalog(self.products, self.retailer, self.enrichment)
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(catalog))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base_url) as response:
                page = response.read().decode("utf-8")
                self.assertIn("No AI, LLM, or shopping workflow", page)

            with urlopen(f"{base_url}/api/options") as response:
                options = json.load(response)
                self.assertEqual(options["retailer"], "CALPAK")
                self.assertEqual(options["product_count"], 3)
                self.assertFalse(options["synthetic_stock"])
                self.assertIn("Carry-On Luggage", options["categories"])

            with urlopen(f"{base_url}/api/products?category=Carry-On+Luggage&page_size=1") as response:
                results = json.load(response)
                self.assertEqual(results["total"], 2)
                self.assertEqual(len(results["products"]), 1)
                self.assertEqual(results["page_size"], 1)

            with self.assertRaises(HTTPError) as error:
                urlopen(f"{base_url}/api/products?min_price=invalid")
            self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
