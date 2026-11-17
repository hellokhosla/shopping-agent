import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backend.catalog import build_products, load_catalog
from retail_agent.config import load_retailer
from retail_agent.models import ONE_SIZE

BACKEND = Path(__file__).resolve().parents[1]
NORDSTROM_CONFIG = BACKEND / "config" / "retailers" / "nordstrom.json"
CALPAK_CONFIG = BACKEND / "config" / "retailers" / "calpak.json"


def nordstrom_row(
    sku: str,
    *,
    tag: str = "Dresses",
    category: str = "Clothing",
    price: str = "100",
    color: str = "410",
) -> dict[str, str]:
    return {
        "SKU": sku,
        "PRODUCT_NAME": f"Demo dress {sku}",
        "BRAND": "Example",
        "PRICE_CURRENT": price,
        "PRICE_RETAIL": "150",
        "REVIEW_RATING": "4.5",
        "REVIEW_COUNT": "25",
        "PROMOTION": "Sale",
        "COLOR": color,
        "CATEGORY": category,
        "SUBCATEGORY": tag,
    }


def calpak_row(
    sku: str,
    *,
    category: str = "Carry-On Luggage",
    available: str = "true",
    option: str = "MATTE BLACK",
) -> dict[str, str]:
    return {
        "sku": sku,
        "title": f"Demo bag {sku}",
        "vendor": "Collection",
        "price": "120.00",
        "compare_at_price": "150.00",
        "option1_value": option,
        "product_type": category,
        "tags": "Travel|Carry-On",
        "available": available,
        "description_text": "A demo travel bag with a padded sleeve.",
    }


class CatalogIngestionTests(unittest.TestCase):
    def test_no_argument_loader_preserves_dataframe_interface(self):
        frame = pd.DataFrame(
            [
                {"product_id": 1, "available": True},
                {"product_id": 1, "available": True},
                {"product_id": 2, "available": False},
            ]
        )
        with patch("backend.legacy_catalog._catalog", None), patch(
            "backend.legacy_catalog.pd.read_csv", return_value=frame
        ) as read_csv:
            result = load_catalog()
            self.assertEqual(result["product_id"].tolist(), [1])
            self.assertIs(load_catalog(), result)
            read_csv.assert_called_once()

    def test_configured_loader_preserves_enriched_catalog_interface(self):
        retailer, enrichment = load_retailer(CALPAK_CONFIG)
        frame = pd.DataFrame([calpak_row("demo")])
        with patch("backend.catalog.pd.read_csv", return_value=frame):
            result = load_catalog(retailer, enrichment, use_cache=False)
        self.assertEqual(result.by_sku["demo"].stock, (("carry-on/cabin", 1),))

    def test_nordstrom_deduplicates_maps_colors_and_synthesizes_stock(self):
        retailer, enrichment = load_retailer(NORDSTROM_CONFIG)
        frame = pd.DataFrame(
            [
                nordstrom_row("keep", tag="Dresses"),
                nordstrom_row("keep", tag="Evening"),
                nordstrom_row("drop-category", category="New Arrivals"),
                nordstrom_row("drop-tag", tag="Fine Jewelry"),
                nordstrom_row("drop-price", price="0"),
            ]
        )

        products = build_products(frame, retailer, enrichment)
        self.assertEqual(len(products), 1)
        product = products[0]
        self.assertEqual(product.sku, "keep")
        self.assertEqual(product.tags, frozenset({"Dresses", "Evening", "Clothing"}))
        self.assertEqual((product.color_family, product.color_shade), ("blue", "navy"))
        self.assertEqual(product.size_system, "apparel")
        self.assertTrue(product.stock_is_synthetic)
        self.assertEqual(product.stock, build_products(frame, retailer, enrichment)[0].stock)
        self.assertEqual((product.price, product.was_price, product.rating, product.review_count),
                         (100, 150, 4.5, 25))

    def test_calpak_maps_luggage_size_and_source_availability(self):
        retailer, enrichment = load_retailer(CALPAK_CONFIG)
        products = build_products(
            pd.DataFrame(
                [
                    calpak_row("available"),
                    calpak_row("sold-out", available="false"),
                    calpak_row("other-size", category="Medium Luggage", option="NAVY"),
                    calpak_row("gift-card", category="Gift Cards"),
                ]
            ),
            retailer,
            enrichment,
        )
        by_sku = {product.sku: product for product in products}

        self.assertEqual(set(by_sku), {"available", "sold-out", "other-size"})
        self.assertEqual(by_sku["available"].stock, (("carry-on/cabin", 1),))
        self.assertTrue(by_sku["available"].in_stock)
        self.assertFalse(by_sku["available"].stock_is_synthetic)
        self.assertEqual(by_sku["sold-out"].stock, (("carry-on/cabin", 0),))
        self.assertFalse(by_sku["sold-out"].in_stock)
        self.assertEqual(by_sku["other-size"].stock, (("medium check-in", 1),))
        self.assertEqual(by_sku["available"].brand, "CALPAK")
        self.assertEqual(by_sku["available"].sizes_in_stock, ["carry-on/cabin"])
        self.assertTrue(by_sku["available"].description)

    def test_unrecognized_source_availability_is_not_silently_accepted(self):
        retailer, enrichment = load_retailer(CALPAK_CONFIG)
        with self.assertRaisesRegex(ValueError, "Unrecognized source availability"):
            build_products(
                pd.DataFrame([calpak_row("bad", available="maybe")]),
                retailer,
                enrichment,
            )

    def test_one_size_system_uses_source_availability_without_invented_size(self):
        retailer, enrichment = load_retailer(CALPAK_CONFIG)
        product = build_products(
            pd.DataFrame([calpak_row("accessory", category="Travel Accessories")]),
            retailer,
            enrichment,
        )[0]
        self.assertEqual(product.size_system, "one_size")
        self.assertEqual(product.stock, ((ONE_SIZE, 1),))
        self.assertFalse(product.stock_is_synthetic)


if __name__ == "__main__":
    unittest.main()
