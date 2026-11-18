# How catalog search works

_Notes for the team discussion · Nov 17, 2026_

This note explains how a shopper's message becomes a ranked list of products. It covers the methods used today
(exact filters and lexical search), the method that is built but switched off (semantic search), and the one that
is only proposed (a reranker). It ends with worked examples and the questions to settle before turning semantic
search on.

Code: [`backend/agent_graph.py`](backend/agent_graph.py) (the pipeline) and
[`backend/catalog_search.py`](backend/catalog_search.py) (the SQL). Schema: [`database.md`](database.md).

---

## 1. Status

| Stage | What it does | Status |
|---|---|---|
| Extraction | An LLM turns the message into a `SearchRequest` | **Live** |
| Exact filters | Hard limits: type, brand, colour, size, price, stock | **Live** |
| Lexical search | Ranks by matching words (Postgres full text) | **Live** |
| Near misses | Relaxed price and shade, labelled with why they missed | **Live** |
| Semantic search | Ranks by meaning (pgvector embeddings) | **Code ready, no embeddings yet.** On hold until the Neon storage plan is confirmed |
| Fusion (RRF) | Merges the lexical and semantic rankings | **Code ready**; becomes active once semantic search is on |
| Reranker | Re-scores the top results with a stronger model | **Proposed, not built** |
| Occasion and style labels | `occasion_tags` / `style_tags` per product | **Deferred.** Semantic search should cover most of this; we revisit only if evals show gaps |

---

## 2. The pipeline at a glance

```
Shopper: "Navy blazer under $150 in size M"
   │
   ▼
① EXTRACT (LLM)          → SearchRequest {product_types:[blazers], colour:navy, size:M, max_price:150}
   │
   ▼
② ONE SQL QUERY ─────────────────────────────────────────────────────────────┐
   │  a. ELIGIBLE   exact filters decide who is allowed in                    │
   │  b. LEXICAL    rank eligible products by matching words   (top 50)       │
   │  c. SEMANTIC   rank eligible products by meaning          (top 50)       │
   │  d. FUSE       combine both ranks with RRF → top 20                       │
   └──────────────────────────────────────────────────────────────────────────┘
   │
   ▼
③ NEAR MISSES            only if fewer than 3 results: relax price (+10%) and shade, label why
   │
   ▼
④ RERANK (proposed)      a stronger model re-scores the top N and reorders them
   │
   ▼
⑤ COMPARE (LLM)          picks the best 2–4 and writes the answer; picks not in the results are dropped
```

Two points matter most:

- **Filters and ranking are separate.** Exact filters decide *which* products can appear. Lexical and semantic
  search only decide the *order* of those products. A $300 blazer can never appear in an "under $150" search,
  however well it matches.
- **Steps a–d are one database round trip.** The database does the filtering, both rankings and the fusion in a
  single SQL statement (common table expressions). The reranker, if added, is a separate call afterwards.

---

## 3. Step ① Extraction

An LLM fills a `SearchRequest` from the message. Its prompt lists the catalog's real product types, departments,
sizes and colours (from `catalog_facets`, cached per retailer), so it can only choose values that exist.

| Field | Kind | Example |
|---|---|---|
| `product_types`, `department`, `brand`, `colour`, `size`, `size_classes`, `min_price`, `max_price` | **Hard filters** | "under $150" → `max_price: 150` |
| `query` | **Ranking words**: whatever is left that describes the item | "satin midi", "hard shell expandable" |

Rule: fill only what the shopper said. Never guess a size, budget or colour.

---

## 4. Step ②a Exact filters (the eligible set)

Exact filters are plain SQL `WHERE` conditions. Product-level filters run on `products`; price, size, colour and
stock run on `variants`, because one product has many colour/size variants with their own price and stock.

```sql
eligible AS (
  SELECT p.product_id FROM products p
  WHERE p.retailer_id = 'nordstrom' AND p.is_active
    AND p.product_type = ANY('{blazers}')
    AND EXISTS (SELECT 1 FROM variants v
                WHERE v.product_id = p.product_id
                  AND v.in_stock
                  AND v.price <= 150
                  AND v.size_norm IN ('M', 'ONE_SIZE')
                  AND v.colour_family = 'blue' AND v.colour_shade = ANY('{navy}')))
```

A product is eligible if **at least one variant** satisfies every variant condition.

| Filter | How it matches |
|---|---|
| Brand | Exact (case-insensitive), else the closest name by trigram similarity: "calpack" → CALPAK. No close brand → zero results |
| Colour | Shopper word → colour family plus shades ("navy" → family blue, shade navy). A word not in the vocabulary is ignored, with a note |
| Size | Exact normalised size, or `ONE_SIZE` |
| Price | Per variant, so a product qualifies if any variant is in budget |
| Stock | `in_stock_only` is on by default |

**Why price is never part of semantic search:** embeddings are poor at numbers ("$150" and "$1,500" look almost
the same to them), and prices change often. Numbers belong in filters.

---

## 5. Step ②b Lexical search (live)

Lexical search ranks by **the words themselves**. Each product has a `search_tsv` column: a Postgres full-text
index built automatically from its fields. Words are lowercased and stemmed ("jackets" → "jacket", "classy" →
"classi"), and each field has a weight:

| Weight | Fields | Why |
|---|---|---|
| A (1.0) | brand, product line, title | A word in the name is the strongest signal |
| B (0.4) | product type, source categories | Strong but broad |
| C (0.2) | tags, best_for, occasion/style tags | Helpful, partly inferred |
| D (0.1) | description | Long and noisy |

**How a query runs.** The `query` words are joined with **OR**, so a product needs only one of them to match.
`ts_rank_cd` then scores each match, favouring products that match more words, in heavier fields, close together.
Ties break by rating.

```sql
lex AS (
  SELECT p.product_id,
         row_number() OVER (ORDER BY ts_rank_cd(p.search_tsv, q) DESC, p.rating DESC) AS r
  FROM products p JOIN eligible USING (product_id),
       to_tsquery('english', 'satin | midi') AS q
  WHERE p.search_tsv @@ q
  LIMIT 50)
```

**Strengths:** exact words, brand names, model names ("Vault", "Etiennette"), materials ("wool", "satin").

**Weaknesses:**
- **Synonyms and meaning are invisible.** "classy" will not match a dress titled "Elegant Slip Dress".
  "dinner date" will not match "evening".
- **The padding problem (today only).** When semantic search is off, eligible products with *no* keyword match
  are appended after the keyword hits, ordered by rating (the `fill` step). This means a vague query never returns
  zero results; it returns popular but possibly unrelated items. Each result carries `keyword_match: true/false`,
  so the compare step can tell the difference.

---

## 6. Step ②c Semantic search (built, switched off)

Semantic search ranks by **meaning**, using embeddings: lists of numbers (here 1,024) produced by an embedding
model, where texts with similar meaning get nearby vectors even when they share no words.

### At load time (once per product, re-run only when the text changes)

1. The loader builds one readable paragraph per product, `search_text`:
   ```
   Etiennette B Good Wool Suit Jacket. Brand: Theory. Type: blazer.
   Categories: Blazers, Suits & Separates; Coats & Jackets. Colours: blue
   ```
   Price and stock are deliberately left out.
2. An embedding model turns that paragraph into a vector, stored in `products.embedding` (pgvector) with an
   HNSW index for fast nearest-neighbour lookups.
3. If a reload changes a product's `search_text`, the loader clears its embedding, so the next embed run only
   processes changed products.

### At query time (once per shopper message)

1. Embed the descriptive part of the request (e.g. "classy dinner date dress") with **the same model**.
2. Rank eligible products by cosine distance to that vector:
   ```sql
   sem AS (
     SELECT p.product_id, row_number() OVER (ORDER BY p.embedding <=> :query_vector) AS r
     FROM products p JOIN eligible USING (product_id)
     LIMIT 50)
   ```

**Strengths:** vague and style language ("classy", "something for camping"), synonyms, occasions, misspellings.
This is why we expect not to need hand-made occasion/style labels.

**Weaknesses:** weaker than lexical search on exact names and codes; can return items that are "about the same
thing" but wrong in a detail; quality depends on how rich `search_text` is (Nordstrom's is short: title, brand,
type, categories and colours; there are no descriptions).

---

## 7. Step ②d Fusion: Reciprocal Rank Fusion (RRF)

Once both rankings exist, they are merged. The raw scores can't simply be added: a lexical score of 0.08 and a
cosine similarity of 0.83 are on different scales and mean different things. RRF uses **ranks only**:

```
RRF score = 1 / (60 + lexical rank)  +  1 / (60 + semantic rank)
```

A product missing from one list contributes 0 for that list. `60` is the standard damping constant (`RRF_K`); it
stops the difference between rank 1 and rank 2 from dominating.

**Example** (illustrative), query "classy satin dress":

| Product | Lexical rank | Semantic rank | RRF score | Final position |
|---|---|---|---|---|
| Satin Midi Dress | 3 | 1 | 1/63 + 1/61 = **0.0323** | 1 |
| Classy Wrap Dress | 1 | 12 | 1/61 + 1/72 = **0.0303** | 2 |
| Silk Slip Dress (no keyword hit) | — | 2 | 1/62 = **0.0161** | 3 |
| Satin Pajama Set | 2 | — | 1/62 = **0.0161** | 4 |

Products both methods agree on rise to the top. A product only one method likes still gets in, lower down.
The top 20 go on to the next step.

**An RRF score is not a confidence.** It says only "this is ahead of that". To decide "these results are weak,
ask the shopper", we need another signal: no lexical match plus a large cosine distance, or a reranker score
(section 9).

---

## 8. Step ③ Near misses (live)

If fewer than 3 products pass the exact filters, the same query runs again with relaxed limits:

- **Price:** up to 10% over budget.
- **Colour:** any shade in the same family (asked for "red" → burgundy is allowed).
- **Size:** never relaxed. A size that doesn't fit is not a near miss.

Each near miss is labelled, e.g. `["$4 over your budget", "burgundy, not red"]`, and the answer must say why it
missed.

---

## 9. Step ④ Reranker (proposed)

### What it is

The rankers in step ② are fast because they compare the query with each product **independently**: lexical
search counts words, and semantic search compares two vectors that were computed separately. A **reranker** (a
cross-encoder) is slower but more accurate: it reads the query and one product's text **together** and outputs a
relevance score from 0 to 1. Because it is too slow to run on thousands of products, it runs only on the
shortlist that step ② already produced.

Options: a hosted rerank model (Voyage rerank, Cohere Rerank) or a small LLM asked to score each item.

### Step by step: what it does with 10 results

**Shopper:** "something classy for a dinner date under $200"
**Extraction:** `max_price: 200`, `department: clothing`, `query: "classy dinner date"`

**1. The SQL query runs once** (filters → lexical + semantic → RRF) and returns its top 10 in RRF order:

| RRF pos | Product | Lex rank | Sem rank |
|---|---|---|---|
| 1 | Satin Midi Slip Dress | — | 1 |
| 2 | "Date Night" Graphic Tee | 1 | 9 |
| 3 | Tailored Wool Blazer | — | 2 |
| 4 | Pleated Silk Skirt | — | 3 |
| 5 | Classic Oxford Shirt | 2 | 14 |
| 6 | One-Shoulder Cocktail Dress | — | 4 |
| 7 | Dinner Party Apron | 3 | — |
| 8 | Wide-Leg Crepe Trousers | — | 5 |
| 9 | Cable Knit Sweater | — | 6 |
| 10 | Velvet Mini Dress | — | 7 |

The tee and the apron are high only because they contain the words "date" and "dinner".

**2. Build pairs.** For each of the 10, pair the shopper's text with that product's `search_text`:
`("something classy for a dinner date", "Satin Midi Slip Dress. Brand: … Type: dresses. Colours: black")`

**3. Score.** Send all 10 pairs to the reranker in **one API call**. It returns a relevance score for each.

**4. Reorder by that score, and drop anything below a threshold** (for example 0.30; tuned with evals):

| New pos | Product | Rerank score | Old pos | Kept? |
|---|---|---|---|---|
| 1 | One-Shoulder Cocktail Dress | 0.91 | 6 | ✅ |
| 2 | Satin Midi Slip Dress | 0.89 | 1 | ✅ |
| 3 | Velvet Mini Dress | 0.82 | 10 | ✅ |
| 4 | Tailored Wool Blazer | 0.74 | 3 | ✅ |
| 5 | Pleated Silk Skirt | 0.70 | 4 | ✅ |
| 6 | Wide-Leg Crepe Trousers | 0.55 | 8 | ✅ |
| 7 | Classic Oxford Shirt | 0.38 | 5 | ✅ |
| 8 | Cable Knit Sweater | 0.21 | 9 | ❌ below threshold |
| 9 | "Date Night" Graphic Tee | 0.12 | 2 | ❌ |
| 10 | Dinner Party Apron | 0.04 | 7 | ❌ |

(Scores are illustrative.)

**5. Use the top score as a confidence gate.**
- Top score high (e.g. ≥ 0.6): pass the kept items to the compare step.
- Top score low: results are weak, so ask the shopper a clarifying question instead of presenting them.

**6. Compare** receives the 7 kept products, in the new order, with their scores.

### Cost and placement

- One extra API call per search, typically 100–300 ms, for 10–50 products.
- It does **not** change which products are eligible. It only reorders and trims what step ② returned, so it can
  never bring back a product the filters excluded.
- Rerank 20–50 rather than 10 if latency allows: the reranker can only promote items that made the shortlist.

---

## 10. Worked examples

### Example 1: specific request, exact filters do the work
**"Navy Theory blazer under $150 in size M"** (Nordstrom)

- Extraction: `product_types: [blazers], brand: Theory, colour: navy, size: M, max_price: 150`, no `query`.
- Filters: very narrow eligible set.
- Ranking: no query words, so products are ordered by rating and review count.
- If fewer than 3 match: near misses such as "$9 over your budget" or "midnight, not navy".
- Semantic search and the reranker add little here; the filters carry it.

### Example 2: descriptive words, lexical search shines
**"Satin midi dress in black"**

- Extraction: `product_types: [dresses], colour: black, query: "satin midi"`.
- Lexical: titles containing "satin" and "midi" rank first (weight A); products with only one of the words
  follow.
- Semantic (when on): agrees on the satin midis and also surfaces "silk slip dress, calf length", which has
  neither word.
- RRF: items both methods agree on go first.

### Example 3: vague style, the case semantic search is for
**"Something classy for a dinner date under $200"**

- Extraction: `max_price: 200, query: "classy dinner date"`, no type.
- **Lexical only (today):** matches "date" and "dinner" literally (graphic tee, apron); everything else is
  rating-ordered padding with `keyword_match: false`.
- **With semantic search:** dresses, blazers and silk skirts rank high by meaning.
- **With a reranker:** the tee and apron are pushed out (see section 9).

### Example 4: luggage with near misses
**"Red carry-on under $200"** (Calpak)

- Extraction: `size_classes: [carry_on], colour: red, max_price: 200`.
- Filters: carry-on size class, red shades, ≤ $200, in stock.
- If fewer than 3 match: near misses at up to $220, or in the red family but another shade, each labelled
  ("$15 over your budget", "burgundy, not red").

### Example 5: a brand the retailer doesn't carry
**"A jacket like Zara's"**

- Extraction: `brand: Zara`.
- Brand lookup finds no exact or close brand → the request is marked impossible → zero results with the note
  "No brand like 'Zara' at this retailer."
- Known gap: the shopper meant a *style*, not the brand. Better behaviour would be to drop the brand filter and
  move "Zara-style" into the ranking words, telling the shopper we don't carry Zara.

---

## 11. Methods compared

| Method | Good at | Weak at | Status |
|---|---|---|---|
| Exact filters | Hard limits: price, size, colour, stock, type, brand | Anything fuzzy | Live |
| Lexical (full text) | Exact words, names, materials | Synonyms, style, occasion | Live |
| Semantic (embeddings) | Meaning, vague and style language | Exact names and codes; depends on text quality | Built, off |
| RRF fusion | Combining rankings on different scales | Gives order, not confidence | Built, off |
| Reranker (cross-encoder) | Precise final ordering; gives a usable confidence score | Adds latency and cost; only sees the shortlist | Proposed |
| Query rewriting (HyDE) | Very short or vague queries: an LLM writes an "ideal product" description and we embed that | Extra LLM call | Option |
| Occasion/style labels | Predictable occasion matching | Offline LLM pass per product; can be wrong | Deferred |
| Agentic search (LLM calls search repeatedly) | Outfits, multi-step requests | Cost, less predictable | Option, for outfits later |

---

## 12. Known gaps today

1. **Vague queries return padding.** Without semantic search, "classy" queries return rating-ordered items that
   may be unrelated.
2. **No clarify route.** The graph always searches; there is no branch for "too vague" or "out of scope".
3. **Outfits are a single search.** "Outfit for a wedding" isn't split into dress / shoes / bag searches.
4. **Unknown brand blocks the search** (example 5).
5. **Extracted types and departments aren't validated** against the facets after extraction; an invented value
   filters everything out, and the "no results" message then blames budget, colour or size.

---

## 13. Questions for the developer discussion

1. **Neon storage.** 122k products × 1,024 dimensions × 4 bytes ≈ **500 MB of vectors plus a similar amount
   for the HNSW index**. Does our Neon plan allow that? If not: `halfvec` (half the size, minimal quality loss)
   or 512 dimensions.
2. **Embedding model.** Voyage (`voyage-3.5`, 1,024 dimensions natively) or OpenAI `text-embedding-3-small` with
   `dimensions=1024` (reuses our existing OpenAI key and dependency; no schema change). The one-off backfill is
   about 4M tokens, well under $1.
3. **Reranker.** Hosted model or small LLM? What latency budget per search?
4. **Confidence gate.** What do we do with weak results: ask a clarifying question, or show them with a caveat?
5. **Text quality.** Nordstrom `search_text` has no descriptions and some product types are wrong (e.g. shorts
   typed as `blazers_suits_separates`). Fix before embedding?

### Work needed to turn semantic search on

| Change | Size |
|---|---|
| `backend/embed_catalog.py`: embed rows where `embedding IS NULL` in batches; drop and rebuild the HNSW index around the backfill | ~100–150 lines |
| Search node: embed the shopper text and pass `query_vector` to `search_catalog` | ~10–20 lines |
| Config for the model name; tests with a fake embedder | small |

The schema, the index, change detection and the fusion SQL already exist.
