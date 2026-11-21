import unittest
from unittest.mock import patch

from backend.agent_graph import Comparison, Pick
from backend.catalog_search import ProductHit, SearchRequest, SearchResult, VariantHit

import app


def hit(product_id, *, near=False, url="https://example.com/product"):
    variant = VariantHit(
        variant_id=product_id, sku=None, colour_raw=None, colour_family=None,
        colour_shade=None, size="ONE_SIZE", price=110 if near else 90,
        was_price=120, in_stock=True, image_url=None,
    )
    return ProductHit(
        product_id=product_id, retailer_id="calpak", title=f"Bag {product_id}",
        brand="CALPAK", product_type="bag", department="bags", size_class=None,
        min_price=variant.price, max_price=variant.price, rating=None, review_count=None,
        promotion=None, image_url=None, product_url=url, synthetic_flags=[],
        is_near_miss=near, miss_reasons=["$10 over your budget"] if near else [],
        variants=[variant],
    )


class StorefrontIntegrationTests(unittest.TestCase):
    def test_graph_picks_render_with_real_prices_and_near_miss_reasons(self):
        result = SearchResult(
            request=SearchRequest(retailer_id="calpak"),
            hits=[hit(1)], near_misses=[hit(2, near=True)],
        )
        comparison = Comparison(summary="Found <bags>.", picks=[
            Pick(product_id=2, why="Roomy", trade_off="Heavier"),
            Pick(product_id=1, why="Light", trade_off="Smaller"),
            Pick(product_id=999, why="Invented", trade_off="Unknown"),
        ])
        with patch("app.run", return_value={"result": result, "comparison": comparison}) as run:
            answer = app.respond("carry-on under $100")
        run.assert_called_once_with("carry-on under $100", retailer_id="calpak")
        self.assertIn("Found &lt;bags&gt;.", answer)
        self.assertLess(answer.index("Bag 2"), answer.index("Bag 1"))
        self.assertIn("Near miss", answer)
        self.assertIn("$10 over your budget", answer)
        self.assertIn("$110.00", answer)
        self.assertIn("Roomy", answer)
        self.assertNotIn("Invented", answer)
        self.assertNotIn("placeholder", answer.lower())

    def test_no_results_shows_backend_message_without_fake_cards(self):
        result = SearchResult(request=SearchRequest(retailer_id="calpak"), hits=[])
        comparison = Comparison(summary="No matching items.", picks=[])
        with patch("app.run", return_value={"result": result, "comparison": comparison}):
            answer = app.respond("unknown item")
        self.assertIn("No matching items.", answer)
        self.assertNotIn("pc-card", answer)

    def test_rejects_unsafe_product_links(self):
        result = SearchResult(request=SearchRequest(retailer_id="calpak"), hits=[hit(1, url="javascript:alert(1)")])
        comparison = Comparison(summary="Match.", picks=[Pick(product_id=1, why="Good", trade_off="None")])
        with patch("app.run", return_value={"result": result, "comparison": comparison}):
            answer = app.respond("bag")
        self.assertIn("Bag 1", answer)
        self.assertNotIn("javascript:", answer)
        self.assertNotIn("View product", answer)


if __name__ == "__main__":
    unittest.main()
