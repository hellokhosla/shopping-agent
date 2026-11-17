import os
import unittest

from backend.agent_graph import Comparison, Pick, build_graph, run
from backend.catalog_search import ProductHit, SearchRequest, SearchResult, VariantHit

FACETS = {
    "product_types": ["blazer", "dress"],
    "departments": ["clothing"],
    "size_classes": [],
    "sizes": ["M", "ONE_SIZE"],
    "colour_families": ["blue"],
}


def _hit(product_id: int, title: str, *, near: bool = False) -> ProductHit:
    variant = VariantHit(
        variant_id=product_id * 10, sku=None, colour_raw="410", colour_family="blue", colour_shade="navy",
        size="M", price=120.0, was_price=None, in_stock=True, image_url=None,
    )
    return ProductHit(
        product_id=product_id, retailer_id="nordstrom", title=title, brand="Theory", product_type="blazer",
        department="clothing", size_class=None, min_price=120.0, max_price=120.0, rating=4.2, review_count=10,
        promotion=None, image_url=None, product_url=None, synthetic_flags=["sizes", "stock"],
        is_near_miss=near, miss_reasons=["$5 over your budget"] if near else [], variants=[variant],
    )


class FakeModel:
    """Stands in for ChatOpenAI: returns canned structured outputs and records the prompts it saw."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        model = self

        class Runnable:
            def invoke(self, messages):
                model.calls.append((schema, messages))
                return model.outputs[schema]

        return Runnable()


class OfflineGraphTests(unittest.TestCase):
    def setUp(self):
        self.searched = []

    def build(self, extracted, comparison, result):
        model = FakeModel({SearchRequest: extracted, Comparison: comparison})

        def search(request):
            self.searched.append(request)
            return result

        return build_graph(chat_model=lambda _: model, search=search, facets=lambda _: FACETS), model

    def test_prompt_flows_through_extract_search_compare(self):
        result = SearchResult(request=SearchRequest(retailer_id="nordstrom"), hits=[_hit(1, "Wool Blazer")])
        comparison = Comparison(summary="One good match.", picks=[Pick(product_id=1, why="Navy, M.", trade_off="None.")])
        graph, model = self.build(
            SearchRequest(retailer_id="nordstrom", product_types=["blazer"], colour="navy", max_price=150),
            comparison, result,
        )
        state = graph.invoke({"retailer_id": "nordstrom", "user_prompt": "Navy blazer under $150", "trace": []})

        self.assertEqual(self.searched[0].product_types, ["blazer"])
        self.assertEqual(state["comparison"].picks[0].product_id, 1)
        self.assertIn("Wool Blazer", state["answer"])
        # The extraction prompt lists the allowed product types; the user's words go in unchanged.
        extract_messages = model.calls[0][1]
        self.assertIn("blazer, dress", extract_messages[0].content)
        self.assertEqual(extract_messages[1].content, "Navy blazer under $150")
        # The comparison skill receives the search results.
        self.assertIn('"product_id": 1', model.calls[1][1][0].content)

    def test_retailer_comes_from_the_session_not_the_model(self):
        result = SearchResult(request=SearchRequest(retailer_id="nordstrom"), hits=[_hit(1, "Wool Blazer")])
        graph, _ = self.build(
            SearchRequest(retailer_id="calpak"), Comparison(summary="ok", picks=[]), result,
        )
        graph.invoke({"retailer_id": "nordstrom", "user_prompt": "blazer", "trace": []})
        self.assertEqual(self.searched[0].retailer_id, "nordstrom")

    def test_invented_product_ids_are_dropped(self):
        result = SearchResult(
            request=SearchRequest(retailer_id="nordstrom"), hits=[_hit(1, "Wool Blazer")],
            near_misses=[_hit(2, "Linen Blazer", near=True)],
        )
        comparison = Comparison(summary="Picks.", picks=[
            Pick(product_id=999, why="made up", trade_off="-"),
            Pick(product_id=2, why="close", trade_off="over budget"),
        ])
        graph, _ = self.build(SearchRequest(retailer_id="nordstrom"), comparison, result)
        state = graph.invoke({"retailer_id": "nordstrom", "user_prompt": "blazer", "trace": []})
        self.assertEqual([p.product_id for p in state["comparison"].picks], [2])
        self.assertTrue(state["comparison"].picks[0].is_near_miss)
        self.assertIn("dropped 1 ungrounded", state["trace"][-1])

    def test_no_results_skips_the_write_up_model(self):
        result = SearchResult(request=SearchRequest(retailer_id="nordstrom"), hits=[])
        graph, model = self.build(SearchRequest(retailer_id="nordstrom"), Comparison(summary="x", picks=[]), result)
        state = graph.invoke({"retailer_id": "nordstrom", "user_prompt": "a tent", "trace": []})
        self.assertEqual(len(model.calls), 1)  # extraction only
        self.assertIn("couldn't find", state["answer"])


# Shopper prompts and the filters the model should extract from them.
PROMPTS = [
    ("nordstrom", "Navy blazer under $150 in size M",
     {"product_types": "blazer", "colour": "navy", "size": "M", "max_price": 150}),
    ("nordstrom", "Show me satin midi skirts",
     {"product_types": "skirt", "query_contains": "satin"}),
    ("nordstrom", "Red dress for a wedding, size M, under $100",
     {"product_types": "dress", "colour": "red", "size": "M", "max_price": 100}),
    ("nordstrom", "Nike sneakers in size 9 under $120",
     {"product_types": "sneakers", "brand": "nike", "size": "9", "max_price": 120}),
    ("nordstrom", "Burgundy dress in size M under $30",
     {"product_types": "dress", "colour": "burgundy", "size": "M", "max_price": 30}),
    ("calpak", "I need a hard shell carry-on suitcase",
     {"size_classes": "carry_on", "query_contains": "hard"}),
]


@unittest.skipUnless(
    os.environ.get("RUN_LLM_TESTS") == "1",
    "set RUN_LLM_TESTS=1 (needs OPENAI_API_KEY and DATABASE_URL) to call the model and the shared database",
)
class LiveGraphTests(unittest.TestCase):
    def test_shopper_prompts(self):
        for retailer_id, prompt, expected in PROMPTS:
            with self.subTest(prompt=prompt):
                state = run(prompt, retailer_id)
                request, result, comparison = state["request"], state["result"], state["comparison"]
                print(f"\n=== [{retailer_id}] {prompt}\n" + "\n".join(state["trace"]) + "\n\n" + state["answer"])

                self.assertEqual(request.retailer_id, retailer_id)
                for field, value in expected.items():
                    if field == "query_contains":
                        self.assertIn(value, (request.query or "").lower())
                    elif field in ("product_types", "size_classes"):
                        self.assertIn(value, getattr(request, field) or [])
                    elif field in ("colour", "brand"):
                        self.assertEqual((getattr(request, field) or "").lower(), value)
                    else:
                        self.assertEqual(getattr(request, field), value)

                found = {h.product_id for h in [*result.hits, *result.near_misses]}
                self.assertTrue(found, "search returned nothing")
                self.assertTrue(comparison.picks)
                self.assertLessEqual({p.product_id for p in comparison.picks}, found)
                self.assertTrue(state["answer"])


if __name__ == "__main__":
    unittest.main()
