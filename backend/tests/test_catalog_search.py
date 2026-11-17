import os
import unittest

from pydantic import ValidationError

from backend.catalog_search import (
    ColourFilter,
    SearchRequest,
    VariantHit,
    carry_on_fit,
    catalog_facets,
    connect,
    exact_search,
    get_products,
    keyword_search,
    miss_reasons,
    near_miss_search,
    resolve_colour,
    search_catalog,
    suggest_brands,
)


def _variant(price: float, shade: str | None, size: str = "M") -> VariantHit:
    return VariantHit(
        variant_id=1, sku=None, colour_raw=None, colour_family="red_pink", colour_shade=shade,
        size=size, price=price, was_price=None, in_stock=True, image_url=None,
    )


class SearchRequestTests(unittest.TestCase):
    def test_size_is_normalized(self):
        self.assertEqual(SearchRequest(retailer_id="nordstrom", size=" m ").size, "M")
        self.assertEqual(SearchRequest(retailer_id="nordstrom", size="8.0").size, "8")
        self.assertIsNone(SearchRequest(retailer_id="nordstrom", size="  ").size)

    def test_blank_text_becomes_none(self):
        request = SearchRequest(retailer_id="nordstrom", query="  ", brand="", colour=None)
        self.assertIsNone(request.query)
        self.assertIsNone(request.brand)

    def test_unknown_size_class_is_rejected(self):
        with self.assertRaises(ValidationError):
            SearchRequest(retailer_id="calpak", size_classes=["overhead"])

    def test_limit_is_capped(self):
        with self.assertRaises(ValidationError):
            SearchRequest(retailer_id="calpak", limit=500)

    def test_request_parses_llm_json(self):
        request = SearchRequest.model_validate_json(
            '{"retailer_id": "nordstrom", "product_types": ["blazer"], "colour": "navy", '
            '"size": "m", "max_price": 150}'
        )
        self.assertEqual((request.product_types, request.size, request.max_price), (["blazer"], "M", 150))


class ColourTests(unittest.TestCase):
    def test_shopper_words_map_to_stored_family_and_shades(self):
        self.assertEqual(resolve_colour("navy"), ColourFilter(word="navy", family="blue", shades=["navy"]))
        self.assertEqual(resolve_colour("Wine").family, "red_pink")
        self.assertEqual(resolve_colour("black").family, "black_grey")

    def test_family_word_accepts_any_shade(self):
        self.assertIsNone(resolve_colour("blue").shades)

    def test_unknown_colour_is_none(self):
        self.assertIsNone(resolve_colour("chartreuse"))
        self.assertIsNone(resolve_colour(None))


class MissReasonTests(unittest.TestCase):
    request = SearchRequest(retailer_id="nordstrom", colour="red", size="M", max_price=100)
    colour = resolve_colour("red")

    def test_exact_variant_has_no_reasons(self):
        self.assertEqual(miss_reasons(_variant(99, "red"), self.request, self.colour), [])

    def test_price_over_budget_rounds_up(self):
        self.assertEqual(miss_reasons(_variant(103.5, "red"), self.request, self.colour), ["$4 over your budget"])

    def test_adjacent_shade_and_unknown_shade(self):
        self.assertEqual(miss_reasons(_variant(90, "burgundy"), self.request, self.colour), ["burgundy, not red"])
        self.assertEqual(
            miss_reasons(_variant(90, None), self.request, self.colour), ["shade not confirmed, not red"]
        )


@unittest.skipUnless(os.environ.get("RUN_DB_TESTS") == "1", "set RUN_DB_TESTS=1 to query the shared database")
class LiveDatabaseTests(unittest.TestCase):
    """Read-only queries against the loaded Neon catalog (database.md section 11)."""

    @classmethod
    def setUpClass(cls):
        cls._ctx = connect()
        cls.conn = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def assert_variants_match(self, hits, *, max_price=None, size=None, family=None, shades=None):
        for hit in hits:
            self.assertTrue(hit.variants, hit.title)
            for v in hit.variants:
                self.assertTrue(v.in_stock)
                if max_price is not None:
                    self.assertLessEqual(v.price, max_price)
                if size is not None:
                    self.assertIn(v.size, (size, "ONE_SIZE"))
                if family is not None:
                    self.assertEqual(v.colour_family, family)
                if shades is not None:
                    self.assertIn(v.colour_shade, shades)

    def test_exact_navy_blazer_under_150_size_m(self):  # 11.1
        result = exact_search(
            SearchRequest(retailer_id="nordstrom", product_types=["blazer"], colour="navy", size="M", max_price=150),
            conn=self.conn,
        )
        self.assertTrue(result.hits)
        for hit in result.hits:
            self.assertEqual((hit.retailer_id, hit.product_type), ("nordstrom", "blazer"))
        self.assert_variants_match(result.hits, max_price=150, size="M", family="blue", shades=["navy"])

    def test_keyword_satin_midi_needs_both_words(self):  # 11.2
        result = keyword_search(SearchRequest(retailer_id="nordstrom", query="satin midi"), conn=self.conn)
        self.assertTrue(result.hits)
        self.assertEqual([h.lex_rank for h in result.hits], list(range(1, len(result.hits) + 1)))
        top = result.hits[0].title.lower()
        self.assertIn("satin", top)
        self.assertIn("midi", top)

    def test_keyword_any_finds_at_least_as_many_as_all(self):
        request = SearchRequest(retailer_id="calpak", query="hard shell expandable", limit=50)
        every = keyword_search(request, match="all", conn=self.conn)
        some = keyword_search(request, match="any", conn=self.conn)
        self.assertGreaterEqual(len(some.hits), len(every.hits))

    def test_hybrid_keeps_hard_filters_and_ranks_keyword_hits_first(self):  # 11.4 without vectors
        result = search_catalog(
            SearchRequest(retailer_id="calpak", query="hard shell", product_types=["carry_on_luggage"]),
            conn=self.conn,
        )
        self.assertTrue(result.hits)
        self.assertTrue(all(h.product_type == "carry_on_luggage" for h in result.hits))
        ranked = [h.lex_rank is not None for h in result.hits]
        self.assertEqual(ranked, sorted(ranked, reverse=True), "keyword hits must come before filler rows")

    def test_near_misses_when_fewer_than_three_exact(self):  # 11.5
        request = SearchRequest(
            retailer_id="nordstrom", product_types=["dress"], colour="burgundy", size="M", max_price=30
        )
        result = search_catalog(request, conn=self.conn)
        self.assertLess(len(result.hits), 3)
        self.assertTrue(result.near_misses)
        exact_ids = {h.product_id for h in result.hits}
        for hit in result.near_misses:
            self.assertTrue(hit.is_near_miss)
            self.assertTrue(hit.miss_reasons)
            self.assertNotIn(hit.product_id, exact_ids)
        # Size is never relaxed, price at most +10%, colour stays in the family.
        self.assert_variants_match(result.near_misses, max_price=33, size="M", family="red_pink")

    def test_near_miss_search_excludes_given_ids(self):
        request = SearchRequest(retailer_id="nordstrom", product_types=["dress"], colour="red", max_price=40)
        first = near_miss_search(request, conn=self.conn)
        self.assertTrue(first)
        again = near_miss_search(request, exclude_ids=[first[0].product_id], conn=self.conn)
        self.assertNotIn(first[0].product_id, {h.product_id for h in again})

    def test_brand_typo_is_resolved(self):
        result = search_catalog(SearchRequest(retailer_id="nordstrom", brand="nikee", limit=5), conn=self.conn)
        self.assertEqual(result.resolved_brand, "Nike")
        self.assertTrue(result.hits)
        self.assertTrue(all(h.brand == "Nike" for h in result.hits))
        self.assertEqual(suggest_brands("calpak", "calpack", conn=self.conn)[0][0], "CALPAK")

    def test_unknown_brand_returns_nothing_with_a_note(self):
        result = search_catalog(SearchRequest(retailer_id="calpak", brand="zzzqqq"), conn=self.conn)
        self.assertEqual(result.hits, [])
        self.assertTrue(result.notes)

    def test_luggage_size_class_filter(self):
        result = exact_search(SearchRequest(retailer_id="calpak", size_classes=["carry_on"]), conn=self.conn)
        self.assertTrue(result.hits)
        self.assertTrue(all(h.size_class == "carry_on" for h in result.hits))

    def test_retailers_never_mix(self):
        calpak = exact_search(SearchRequest(retailer_id="calpak", limit=5), conn=self.conn)
        self.assertTrue(all(h.retailer_id == "calpak" for h in calpak.hits))
        ids = [h.product_id for h in calpak.hits]
        self.assertEqual(get_products("nordstrom", ids, conn=self.conn), [])
        self.assertEqual([p.product_id for p in get_products("calpak", ids[::-1], conn=self.conn)], ids[::-1])

    def test_vector_argument_is_accepted_before_embeddings_exist(self):
        result = search_catalog(
            SearchRequest(retailer_id="calpak", query="carry-on"), query_vector=[0.01] * 1024, conn=self.conn
        )
        self.assertTrue(result.hits)

    def test_carry_on_fit_runs(self):  # 11.6; empty until size_class_dims/airline_limits are seeded
        self.assertIsInstance(carry_on_fit(conn=self.conn), list)

    def test_facets_list_real_values(self):
        facets = catalog_facets("calpak", conn=self.conn)
        self.assertIn("carry_on_luggage", facets["product_types"])
        self.assertIn("carry_on", facets["size_classes"])


if __name__ == "__main__":
    unittest.main()
