import unittest

from backend.database_loader import (
    _attributes,
    _best_for_and_features,
    _clean_tags,
    _colour_family,
    _nordstrom_product_type,
    _product_url,
    _size_norm,
)
from backend.configuration import load_retailer


class DatabaseLoaderMappingTests(unittest.TestCase):
    def test_internal_calpak_tags_are_removed_but_shopper_tags_remain(self):
        tags = _clean_tags(
            [
                "Hard Shell",
                "Expandable",
                "New Arrivals",
                "Final Sale",
                "BFCM26",
                "HOTDEAL1",
                "dad25",
                "pc-23019",
                "YCRF_reviews-star-bag-charm",
                "allproducts",
            ]
        )
        self.assertEqual(tags, ["Hard Shell", "Expandable", "New Arrivals", "Final Sale"])

    def test_suit_jacket_uses_canonical_blazer_type(self):
        retailer, _ = load_retailer("backend/config/retailers/nordstrom.json")
        product_type = _nordstrom_product_type(
            "Etiennette B Good Wool Suit Jacket",
            ["Blazers, Suits & Separates", "Coats & Jackets"],
            retailer.category_tags,
        )
        self.assertEqual(product_type, "blazer")

    def test_plural_source_titles_resolve_to_singular_product_types(self):
        retailer, _ = load_retailer("backend/config/retailers/nordstrom.json")
        product_type = _nordstrom_product_type(
            "Floral Midi Dresses",
            ["Dresses"],
            retailer.category_tags,
        )
        self.assertEqual(product_type, "dress")

    def test_unique_source_category_resolves_without_title_keyword(self):
        retailer, _ = load_retailer("backend/config/retailers/nordstrom.json")
        product_type = _nordstrom_product_type(
            "Floral Occasion Gown",
            ["Dresses"],
            retailer.category_tags,
        )
        self.assertEqual(product_type, "dress")

    def test_specific_source_category_wins_over_broad_secondary_tag(self):
        retailer, _ = load_retailer("backend/config/retailers/nordstrom.json")
        product_type = _nordstrom_product_type(
            "Charmed Collar Bra Tank",
            ["Tops", "Activewear"],
            retailer.category_tags,
        )
        self.assertEqual(product_type, "top")

    def test_variant_and_size_fields_are_normalized(self):
        self.assertEqual(_colour_family("red/pink"), "red_pink")
        self.assertEqual(_colour_family("black/grey"), "black_grey")
        self.assertEqual(_size_norm("ONE SIZE"), "ONE_SIZE")
        self.assertEqual(_size_norm("carry-on/cabin"), "CARRY-ON/CABIN")
        self.assertEqual(
            _product_url("https://example.test/products/bag?variant=123&source=demo"),
            "https://example.test/products/bag?source=demo",
        )

    def test_calpak_description_enrichment_extracts_grounded_fields(self):
        description = (
            "Best for: Carry-on travel and weekends. "
            "Features: Hard-Shell Exterior: Protects packed items. "
            "Laptop Sleeve: Fits up to 15 inch laptop."
        )
        best_for, features = _best_for_and_features(description)
        self.assertEqual(best_for, "Carry-on travel and weekends.")
        self.assertEqual(features, ["Hard-Shell Exterior", "Laptop Sleeve"])
        self.assertEqual(_attributes(description), {"laptop_in": 15})


if __name__ == "__main__":
    unittest.main()
