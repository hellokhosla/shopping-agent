# Team 12 Retail Shopping Agent Platform — PRD v2

Nov 15, 2026 · @Prasad Raja

**V1 scope frozen on Nov 15, 2026.** V1 is what the Friday demo shows; V2 items are open and listed at the end. One open V1 item remains: the image-rich dataset decision.

## Pitch

We are building one configurable shopping agent that any retailer can plug into its site, instead of a custom bot per retailer.

A shopper types what they want in plain language, such as "a carry-on under $200" or "a black dress for a wedding under $150". The agent asks one clarifying question only when needed, searches that retailer's catalog, compares the best options with review highlights, and adds the chosen item to the cart.

The retailer configures the catalog source, brand voice and merchandising rules, such as boosting a brand. Boosted items are always labelled and never break the shopper's limits.

The Friday demo runs the same agent on two retailers in different categories, Calpak (luggage) and Nordstrom (apparel), switching only the configuration.

## Problem, buyer and user

Shoppers leave large catalogs without buying because comparing options is tedious, and keyword search and filters can't answer questions asked in natural language.

|  | Buyer | User |
| --- | --- | --- |
| Who | The retailer's e-commerce lead | The retailer's online shoppers |
| Pain | Visitors abandon search; generic chatbots aren't on-brand or grounded in the catalog | Hard to turn a loose need into the right product; filters ignore intent |
| Wants | Higher add-to-cart rate, faster decisions, control over brand voice and merchandising | Right options fast, within budget, with honest comparisons |

Why generative AI fits: shopper questions are open-ended, and good answers combine several product attributes and reviews. An LLM grounded in the catalog can interpret intent and explain trade-offs, while code enforces prices and filters.

## Goals and success metrics

Success means the retailer sees business value and the agent's quality is measured, not just demoed. Targets are set after a first baseline run.

| Type | Metric | What it measures |
| --- | --- | --- |
| Retailer | Add-to-cart rate | Share of conversations ending with an item in the cart |
| Retailer | Time to decision | Turns and seconds from first message to add-to-cart |
| Retailer | Abandonment | Share of conversations ending with no product chosen |
| Quality | Constraint accuracy | Exact matches meet every hard limit; near misses stay inside tolerance and are labelled |
| Quality | Clarify-when-needed / unnecessary questions | Asks on vague requests; doesn't ask on specific ones |
| Quality | Refusal accuracy | Declines policy, competitor and off-topic requests; never declines valid product questions |
| Quality | Boost compliance | Boosted items are always labelled and always exact matches |
| Quality | Comparison faithfulness | Every claim in a comparison matches catalog data or reviews (LLM-as-judge) |
| Cost | Cost and latency per successful task | Compared across versions on the same scenarios |

In the demo, retailer metrics are measured on simulated sessions from the scenario set, not real traffic.

## Scope principles

The platform is designed; the MVP built for Friday proves it on two retailers.

- **One framework, configured per retailer.** No retailer-specific code. A new retailer means new config and data, not new logic.
- **Product questions only.** Search, compare, recommend, build outfits, add to cart. The agent may use outside facts that help choose products (airline size limits), but doesn't plan trips. Policy questions (returns, shipping) get a polite redirect to the retailer's help page.
- **Online inventory only.** No store locations.
- **Human decides.** The agent recommends and adds to cart only when the shopper asks; no payments.
- **Ask, don't guess, but don't over-ask.** At most one round of clarifying questions, only when the answer changes the results.
- **LLM proposes, code enforces.** Prices, sizes, colours, stock and boost rules are checked in code, never by the LLM.
- **Configuration in files.** Each retailer is a config file in the MVP; an admin screen is design only.

## Configuration model

Three layers keep "any retailer" realistic: shared platform code, reusable category packs, and a small retailer config.

| Layer | Shared by | Contains | Example |
| --- | --- | --- | --- |
| Platform code | All retailers | Agent flow, guardrails, search, matching rules, widget | Same for Calpak and Nordstrom |
| Category pack | All retailers selling that category | Key attributes, clarifying questions, comparison factors | Luggage: size class, capacity, weight. Apparel: size, fit, occasion, colour family |
| Retailer config | One retailer | Catalog source and field mapping, category packs used, brand voice, merchandising rules | Calpak config file; Nordstrom config file |

**Retailer can configure vs. platform locks**

| Retailer can configure | Platform locks (can't be turned off) |
| --- | --- |
| Which brands or products to boost | Boosted items are labelled "Boosted" |
| Boost strength (ranking order) | Boosted items must be exact matches; boosting never changes which items qualify |
| Brand voice and tone | No made-up specs, prices or claims; facts come only from catalog and reviews |
| Topics to decline (e.g. competitors) | Scope, privacy and prompt-injection guardrails stay on |
| Catalog source (API, data warehouse, file) | Each retailer's data, config and logs stay isolated |

## Matching rules

Exact matches come first; near misses appear only when needed and are always labelled; boosting changes order, never eligibility. All five rules were approved by the team on Nov 15.

1. **Exact matches first.** Every hard limit (price, size, colour family, category, in stock) is met, checked in code.
2. **Near misses only when exact matches are too few** (fewer than 3). Tolerances: price up to 10% over budget; colour in an adjacent shade of the same family (red allows burgundy or deep pink, not blue). Size is never relaxed.
3. **Every near miss is labelled** with what it misses, e.g. "$12 over your budget" or "burgundy, not red".
4. **Boosted items must be exact matches.** Tolerance never applies to them. A boost moves an item up the ranking, labelled "Boosted"; it never adds an item that wouldn't otherwise qualify.
5. **Total price** used for the budget check is the current online price: PRICE\_CURRENT for Nordstrom, price for Calpak. Neither dataset has shipping or tax.

## MVP requirements (built for Friday)

These 13 requirements are frozen for V1 and are what the live demo shows. Demo levels: L1 (specific item), L2 (vague item with clarifying), L3 (outfit).

| ID | Requirement | Done when |
| --- | --- | --- |
| M1 | Config-driven retailers | Switching the config file switches catalog, category pack, boosted brands and clarifying questions, with no code change |
| M2 | Catalog ingestion | Each CSV loads into one standard product format via a field mapping in its config, with the agreed dataset changes applied |
| M3 | Attribute enrichment (offline) | Colour family, size class and normalised sizes are added at load time; Nordstrom colours come from a code lookup table |
| M4 | Understand the request | Free text becomes structured limits (category, budget, size, colour, occasion, style words) that code validates |
| M5 | Clarify only when needed | One round of up to 3 to 4 short questions together, skipping anything already given; questions come from the category pack |
| M6 | Matching rules | Exact matches, labelled near misses and boost rules behave as in Matching rules |
| M7 | Compare and recommend (L1, L2) | Top 3 options side by side with reasons, ratings and review highlights |
| M8 | Outfit builder (L3) | LLM proposes slots for the occasion (wedding: dress, heels, clutch, earrings; camping: cargo pants, fleece, hiking boots) and a budget split; code finds combinations within the total; 2 to 3 complete outfits at different price points; shopper can swap one item per slot; each outfit shows its total |
| M9 | Carry-on fit check (Calpak) | Luggage dimensions are compared with an airline lookup table; the answer says "typical size for this class" and never guarantees a fit |
| M10 | Reviews | Real rating and count shown where available; synthetic review text (3 to 8, labelled) pre-generated for demo products, generated on first view and cached for the rest, consistent with the rating |
| M11 | Scope and catalog guardrails | Policy questions get a help-page redirect; competitor and off-topic requests are declined; out-of-catalog requests (men's clothing, camping gear) are explained with what the agent can offer; injection attempts are declined |
| M12 | Add to cart | Shopper picks an option or outfit; it's added to a mock cart. No payment |
| M13 | Demo page | Standalone chat page styled as a widget, with a retailer switcher and product cards (Calpak images; Nordstrom image source open) |

## Good to have (designed, not built)

These appear in the system design and on the poster; they're built only if the MVP is done and evaluated early.

| ID | Feature | Why it matters |
| --- | --- | --- |
| G1 | Brand voice per retailer | On-brand tone is a key reason retailers want their own agent |
| G2 | Retailer analytics | What shoppers asked, where they dropped off, what was compared; a strong reason to buy |
| G3 | Prompt-injection protection | Product text can't change the agent's instructions or rankings |
| G4 | Visible decision trace | Shows why the agent asked, filtered, ranked and boosted |
| G5 | Bundles and accessories | "Suitcase plus packing cubes" increases order value |
| G6 | Retailer onboarding | Connect via API or data warehouse; LLM suggests field mapping, a human approves |
| G7 | Admin screen | Retailers edit their config instead of files |
| G8 | Login and memory | Shopper preferences and history, owned by the retailer's customer data |
| G9 | Policy questions | Returns, shipping and warranty answered from official policy text only |

## Out of scope

- **Payments and checkout:** the retailer owns checkout; the agent stops at the cart.
- **Store policies in the MVP:** redirected to the help page (G9 later).
- **In-store inventory and locations.**
- **Competitor comparisons and products from other retailers.**
- **Live retailer integrations:** the demo uses CSV datasets; API and data warehouse connectors are design only.
- **Real reviews:** demo reviews are synthetic.
- **Retailer-specific custom code.**

## Demo retailers and data

Nordstrom is the primary demo retailer and carries most scenarios; Calpak proves configurability and the carry-on check. The Nordstrom dataset holds for V1 while an image-rich alternative is evaluated.

|  | Nordstrom | Calpak |
| --- | --- | --- |
| Role | Primary: L1 to L3 scenarios | Secondary: config switch and carry-on fit |
| Source file | nordstrom product data.csv (Kaggle, May 2022 snapshot) | calpak\_catalog\_variants.csv (Calpak storefront export, Nov 2026) |
| Size | 288,409 rows; 129,343 unique SKUs; women only | 181 products; 1,733 variants; 23 luggage products |
| Has | Category, 81 subcategories, brand, current and retail price, promotion, rating and review count, colour code | Product type, colour name, price, compare-at price, availability per variant, description with "Best for", image URL |
| Missing | Description, sizes, stock, images, colour names, review text | Dimensions, capacity, review text |

### Agreed changes: Nordstrom

1. De-duplicate by SKU (one SKU appears up to 8 times across subcategories); keep its categories as tags.
2. Drop the duplicate New Arrivals listings and Fine Jewelry (prices up to $49,850).
3. Keep the full remaining catalog, not a subset: occasion wear, outdoor wear (hiking boots, cargo pants, fleece, rain jackets) and accessories are all needed.
4. Map colour codes to colour families with a lookup table. The first digit is the family: 0 black/grey/silver, 1 white, 2 brown, 3 green, 4 blue, 5 purple, 6 red/pink, 7 yellow/gold, 8 orange, 9 multi. Check the top \~70 codes (80% of products) by hand; 650 maps to pink.
5. Synthesize sizes per category (dresses XS to XL, shoes 5 to 11, none for bags and jewelry) and stock per size, with a fixed random seed, labelled synthetic.
6. Price is PRICE\_CURRENT; PRICE\_RETAIL shows as "was" when higher; PROMOTION shows as a sale label.
7. Use the real REVIEW\_RATING and REVIEW\_COUNT; about 56% of rows have none.
8. Synthetic review text: pre-generated for demo-scenario products, generated on first view and cached for the rest, consistent with the real rating, labelled synthetic.

### Agreed changes: Calpak

1. Exclude zero-price items (extended warranty, free personalisation).
2. Strip internal tags (e.g. BFCM26, pc-23019); keep meaningful ones such as New Arrivals.
3. Map creative colour names (MUSHROOM, CELADON, DARK CHERRY) to colour families: offline LLM, checked by a person.
4. Size class comes from product type: mini carry-on, carry-on, medium, large.
5. Add dimensions per size class for the luggage categories, labelled "typical size for this class".
6. Add an airline lookup table: major airlines' overhead carry-on and under-seat personal item limits, with source and date.
7. Use real availability per variant as stock, and compare-at price for sale labels.
8. Synthetic review text as for Nordstrom (Calpak has no rating data).

### Open dataset questions

- [ ] Image-rich apparel dataset to replace or supplement Nordstrom. Candidates: Amazon Reviews 2023 (Clothing, Shoes & Jewelry), H&M (Kaggle), Fashion Product Images (Kaggle, Myntra), Shopify storefronts. Time-boxed to Monday Nov 16; check licence, images, prices and colour fields
- [ ] Exact dimensions per luggage size class and their source
- [ ] Which airlines go in the lookup table, and their source
- [ ] Synthetic size distributions and in-stock rates
- [ ] List of demo-scenario products that get pre-generated reviews

## Key scenarios (demo script draft)

Each scenario shows something a filter page can't do; the final prompts will be written against the real data.

| # | Retailer | Level | Shopper says | Expected behaviour | Requirements |
| --- | --- | --- | --- | --- | --- |
| 1 | Nordstrom | L1 | "Navy blazer under $150" | No question; exact matches compared with ratings | M4, M6, M7 |
| 2 | Nordstrom | L2 | "A classy dress for an evening party" | One round: occasion (wedding, cocktail, dinner)? budget? size? colour? Then top 3 with reasons | M5, M7 |
| 3 | Nordstrom | L3 | "Dress me for a wedding, $400 total" | Asks size and colour; 2 to 3 outfits (dress, heels, clutch, earrings) at different totals within $400; shopper swaps one item | M5, M8 |
| 4 | Nordstrom | L3 | "Outfit for a camping weekend under $250" | Slots change: cargo or hiking pants, fleece or rain jacket, hiking boots; no dresses | M8 |
| 5 | Nordstrom | L2 | "Red dress under $100, size M", few exact matches | Exact matches first; labelled near misses (pink family, up to $110) | M6 |
| 6 | Nordstrom | L1 | Same request with the house brand boosted | Boosted exact match moves up, labelled; no boosted near miss | M6 |
| 7 | Calpak | L1 | "A carry-on that fits most airlines" | Compares carry-ons with the airline table; "typical size" caveat | M9 |
| 8 | Switch | — | Similar request after switching Nordstrom to Calpak | Different catalog, questions and boosts; same code | M1 |
| 9 | Either | — | "Return policy?", "Cheaper on Amazon?", "Outfit for my husband", "A tent" | Help-page redirect; decline; explain the catalog covers women's clothing only | M11 |
| 10 | Either | — | Picks an option or outfit | Added to the mock cart | M12 |

**Edge cases for evaluation (not all in the live demo)**

- Contradictory limits ("ball gown under $30"): no exact matches; labelled near misses or a clear explanation.
- Outfit budget too low ("wedding outfit under $60"): says the budget is tight; offers the best partial outfit or asks which item matters most.
- Size still unknown after clarifying: shows items labelled "size not confirmed".
- Ambiguous style words ("classy", "cute", "comfortable"): clarifies, or maps to name keywords and states the assumption.
- Mind changed mid-conversation ("actually make it blue"): updates the limits without restarting.
- Named comparison ("compare these two dresses"): compares directly, no search.
- Injection in the request ("ignore your rules"): declined; rules unchanged.
- Odd prices ($0, extreme): removed at load time.
- Duplicate products: never shown twice.
- Shopper's size out of stock: shown only as a labelled near miss.
- Review generated on first view: results show first; reviews fill in when ready.

## Version ladder

Agency grows version by version; the locked floor and "code enforces limits" never change. Only V1 is built.

|  | V1: Workflow agent | V2: Single autonomous agent | V3: Multi-agent platform |
| --- | --- | --- | --- |
| Status | Built (MVP) | Designed | Designed (future) |
| Who decides the steps | Code | The agent, within step limits | An orchestrator delegating to specialist agents |
| Adds | Two retailers via config, clarify, matching rules, compare, outfits (L1 to L3), carry-on check, cart | Trip packing (L4), image search, live web lookups, brand voice, injection protection, decision trace, policy answers | Retailer onboarding, analytics, login and memory, many retailers |
| Human in the loop | Shopper confirms every add to cart | Same | Same; retailer approves config and field mappings |
| Main trade-off | Cheapest, most predictable, least flexible | More flexible on vague requests; more cost and variance | Scales to many retailers; highest cost and complexity |

Detailed design, cost and latency estimates go in the system design doc.

## V2 open items

Everything discussed for V2 so far; all of it is open and will be designed after the V1 system design. It also covers the good-to-have items G1 to G9.

| Item | What we discussed | Open questions |
| --- | --- | --- |
| Trip packing / capsule wardrobe (L4) | "Pack for 7 days in France, May to June": look up weather, ask about events and taste, plan 6 to 7 looks from reused items (e.g. 2 pants, 4 tops, 1 jacket, 2 shoes) | Live weather search vs. climate data; how to judge capsule quality; mix-and-match planning approach |
| Image search | Shopper uploads a photo ("a necklace like this") and finds similar products | Needs real product images: Calpak has them, Nordstrom doesn't; never use generated images as product photos; how to compare images |
| Live outside knowledge | Web search (e.g. Tavily) for weather and airline rules instead of curated tables | Freshness vs. added latency, cost and injection risk from web content; caching |
| More agent autonomy | Agent chooses its own steps and tools within step limits | Which decisions move from code to the agent; stopping conditions; how to evaluate whole conversations |
| Retailer-facing features | Brand voice, analytics, onboarding via API or data warehouse with LLM-suggested field mapping, admin screen | Which come first; what retailers can change themselves |
| Policy answers | Returns, shipping, warranty from official text only | Liability; how answers quote sources |
| Login and memory | Shopper preferences and history, owned by the retailer's customer data | Privacy, consent, what to remember |
| Multi-agent (V3) | Orchestrator with specialist agents | When the extra cost and complexity is worth it |

## Risks and open questions

The biggest risk is the data: the agent can only filter on attributes the CSVs actually have or that enrichment adds.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| CSVs lack key attributes (colour family, size, category) | Matching rules can't be enforced | Offline enrichment (M3); review data first |
| Synthetic reviews feel fake or contradict specs | Comparison loses credibility | Generate from product attributes; label as synthetic |
| Two catalogs double the data work | Demo slips | Limit each catalog to a demo-sized subset |
| "Framework" claim isn't visible | Looks like two hard-coded bots | Live config switch in the demo (scenario 8) |
| Demo-day failure | Lost demo | Record a backup video by Thursday |

- [ ] Image-rich dataset decision by Monday Nov 16 (see Open dataset questions)
- [ ] Luggage dimensions and airline table: values and sources
- [ ] Specific models within the small and mid tiers (compare on Artificial Analysis); no fine-tuning in V1
- [ ] Roles for Subhra and Gaurav
- [x] Matching rules 2 and 4 approved (Nov 15)
- [x] Boosted brands set per retailer in config files (Nov 15)
- [x] CSV review done (Nov 15)
