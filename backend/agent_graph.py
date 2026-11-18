"""Search-and-compare LangGraph: shopper prompt -> SearchRequest -> catalog search -> comparison write-up.

    extract  (LLM, structured output: SearchRequest)
       |
    search   (code: catalog_search.search_catalog)
       |
    compare  (LLM, comparison write-up skill)   or   no_results (template, no LLM)

The model and temperature come from the retailer config (`llm`). OPENAI_API_KEY is read from the process
environment or from `backend/.env` (git-ignored; don't put API keys in the tracked `backend/.env.local`).

    from backend.agent_graph import run
    state = run("Navy blazer under $150 in size M", retailer_id="nordstrom")
    print(state["answer"])
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Protocol, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .catalog_search import SearchRequest, SearchResult, catalog_facets, search_catalog
from .colors import COLOR_WORDS
from .configuration import RetailerConfig, load_retailer

BACKEND_DIR = Path(__file__).resolve().parent
RETAILER_CONFIG_DIR = BACKEND_DIR / "config" / "retailers"
COMPARISON_SKILL = BACKEND_DIR / "skills" / "comparison_writeup.md"


class Pick(BaseModel):
    product_id: int = Field(description="product_id from the search results; never invented.")
    why: str = Field(description="One sentence on why it fits the shopper's request.")
    trade_off: str = Field(description="One honest trade-off compared with the other picks.")
    is_near_miss: bool = False


class Comparison(BaseModel):
    """What the comparison write-up skill returns."""

    summary: str = Field(description="2-3 sentences answering the shopper.")
    picks: list[Pick] = Field(description="2-4 best matches, best first. Empty if nothing fits.")


class AgentState(TypedDict, total=False):
    retailer_id: str
    user_prompt: str
    request: SearchRequest
    result: SearchResult
    comparison: Comparison
    answer: str
    trace: list[str]


class ChatModel(Protocol):
    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any: ...


@lru_cache(maxsize=None)
def load_retailer_config(retailer_id: str) -> RetailerConfig:
    path = RETAILER_CONFIG_DIR / f"{retailer_id}.json"
    if not path.is_file():
        raise ValueError(f"Unknown retailer {retailer_id!r}; no config at {path}")
    return load_retailer(path)[0]


@lru_cache(maxsize=None)
def _facets(retailer_id: str) -> dict[str, list[str]]:
    return catalog_facets(retailer_id)


def default_chat_model(retailer_id: str) -> ChatModel:
    from langchain_openai import ChatOpenAI

    load_dotenv(BACKEND_DIR / ".env")
    llm = load_retailer_config(retailer_id).llm
    return ChatOpenAI(model=llm.model, temperature=llm.temperature, timeout=60, max_retries=2)


def extraction_prompt(config: RetailerConfig, facets: dict[str, list[str]]) -> str:
    colours = ", ".join(sorted(COLOR_WORDS))
    return f"""You turn a shopper's message into catalog search filters for {config.display_name}.
Catalog scope: {config.guardrails.catalog_scope}

Fill only what the shopper actually said; leave everything else null. Never guess a budget, size or colour.
- retailer_id: always "{config.retailer_id}".
- product_types: choose only from this list, and include close synonyms from it (e.g. both "sweater" and
  "sweaters"). Leave null if no type fits or the shopper didn't name one.
  {", ".join(facets["product_types"])}
- department: one of {", ".join(facets["departments"])}; only if the shopper names a department, not a type.
- colour: the shopper's colour word, lower case, from: {colours}. Null if none or not in the list.
- size: apparel or shoe size exactly as one of: {", ".join(s for s in facets["sizes"] if s != "ONE_SIZE")}.
- size_classes: luggage only, from: {", ".join(facets["size_classes"]) or "none for this retailer"}.
  ("carry-on" -> carry_on; "checked"/"check-in" -> medium and large.)
- brand: only a brand the shopper names (spelling mistakes are fine).
- max_price / min_price: numbers in dollars ("under $150" -> max_price 150).
- query: the remaining descriptive words worth keyword-matching (materials, styles, features, occasion),
  e.g. "satin midi", "hard shell expandable". Don't repeat the colour, size, budget or brand here.
"""


def _compact(result: SearchResult) -> dict[str, list[dict[str, Any]]]:
    """IDs and key facts only (plan.md: compact tool outputs)."""

    def card(hit: Any) -> dict[str, Any]:
        return {
            "product_id": hit.product_id,
            "title": hit.title,
            "brand": hit.brand,
            "product_type": hit.product_type,
            "colours": sorted({v.colour_shade for v in hit.variants if v.colour_shade}),
            "sizes_in_stock": sorted({v.size for v in hit.variants if v.in_stock}),
            "rating": hit.rating,
            "review_count": hit.review_count,
            "promotion": hit.promotion,
            "keyword_match": hit.lex_rank is not None,
            "synthetic_flags": hit.synthetic_flags,
            **({"miss_reasons": hit.miss_reasons} if hit.is_near_miss else {}),
        }

    return {
        "exact_matches": [card(h) for h in result.hits],
        "near_misses": [card(h) for h in result.near_misses],
    }


def render_answer(comparison: Comparison, result: SearchResult) -> str:
    titles = {h.product_id: h.title for h in [*result.hits, *result.near_misses]}
    lines = [comparison.summary, ""]
    for i, pick in enumerate(comparison.picks, 1):
        label = " (near miss)" if pick.is_near_miss else ""
        lines.append(f"{i}. **{titles.get(pick.product_id, pick.product_id)}**{label}: {pick.why} "
                     f"_Trade-off: {pick.trade_off}_")
    return "\n".join(lines).strip()


def build_graph(
    chat_model: Callable[[str], ChatModel] = default_chat_model,
    search: Callable[[SearchRequest], SearchResult] = search_catalog,
    facets: Callable[[str], dict[str, list[str]]] = _facets,
):
    """Compile the graph. Pass `chat_model`/`search`/`facets` to swap in fakes for offline tests."""
    from langgraph.graph import END, START, StateGraph

    def extract(state: AgentState) -> AgentState:
        retailer_id = state["retailer_id"]
        config = load_retailer_config(retailer_id)
        llm = chat_model(retailer_id).with_structured_output(SearchRequest, method="function_calling")
        request = llm.invoke([
            SystemMessage(extraction_prompt(config, facets(retailer_id))),
            HumanMessage(state["user_prompt"]),
        ])
        # The session decides the retailer, never the model.
        request = SearchRequest.model_validate({**request.model_dump(), "retailer_id": retailer_id})
        return {"request": request, "trace": [*state.get("trace", []), f"extract: {request.model_dump(exclude_none=True)}"]}

    def run_search(state: AgentState) -> AgentState:
        result = search(state["request"])
        note = f"search: {len(result.hits)} exact, {len(result.near_misses)} near misses"
        return {"result": result, "trace": [*state["trace"], note, *result.notes]}

    def compare(state: AgentState) -> AgentState:
        retailer_id = state["retailer_id"]
        config = load_retailer_config(retailer_id)
        result = state["result"]
        skill = COMPARISON_SKILL.read_text(encoding="utf-8").format(
            retailer_name=config.display_name,
            user_prompt=state["user_prompt"],
            products_json=json.dumps(_compact(result), indent=1),
        )
        llm = chat_model(retailer_id).with_structured_output(Comparison, method="function_calling")
        comparison = llm.invoke([
            SystemMessage(f"{skill}\n\nBrand voice: {config.brand_voice}"),
            HumanMessage(state["user_prompt"]),
        ])
        # Grounding: drop any pick that isn't in the search results.
        known = {h.product_id: h.is_near_miss for h in [*result.hits, *result.near_misses]}
        grounded = [p.model_copy(update={"is_near_miss": known[p.product_id]})
                    for p in comparison.picks if p.product_id in known]
        dropped = len(comparison.picks) - len(grounded)
        comparison = comparison.model_copy(update={"picks": grounded})
        trace = [*state["trace"], f"compare: {len(grounded)} picks" + (f", dropped {dropped} ungrounded" if dropped else "")]
        return {"comparison": comparison, "answer": render_answer(comparison, result), "trace": trace}

    def no_results(state: AgentState) -> AgentState:
        answer = ("I couldn't find anything matching all of that. Try a higher budget, a different colour, "
                  "or another size.")
        if state["result"].notes:
            answer = " ".join(state["result"].notes) + " " + answer
        return {"comparison": Comparison(summary=answer, picks=[]), "answer": answer,
                "trace": [*state["trace"], "no_results"]}

    def route(state: AgentState) -> str:
        result = state["result"]
        return "compare" if result.hits or result.near_misses else "no_results"

    graph = StateGraph(AgentState)
    graph.add_node("extract", extract)
    graph.add_node("search", run_search)
    graph.add_node("compare", compare)
    graph.add_node("no_results", no_results)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "search")
    graph.add_conditional_edges("search", route, {"compare": "compare", "no_results": "no_results"})
    graph.add_edge("compare", END)
    graph.add_edge("no_results", END)
    return graph.compile()


@lru_cache(maxsize=1)
def _default_graph():
    return build_graph()


def run(user_prompt: str, retailer_id: str) -> AgentState:
    """Run one shopper message through the graph and return the final state."""
    return _default_graph().invoke({"retailer_id": retailer_id, "user_prompt": user_prompt, "trace": []})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ask the shopping agent one question.")
    parser.add_argument("prompt")
    parser.add_argument("--retailer", default="nordstrom", choices=("nordstrom", "calpak"))
    args = parser.parse_args()
    final = run(args.prompt, args.retailer)
    print("\n".join(final["trace"]), "\n")
    print(final["answer"])
