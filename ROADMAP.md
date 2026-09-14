# Product roadmap

The plan of record for this repository. It supersedes the P0–P6 hypothesis
that preceded it; that hypothesis is kept below, with the verdict on each
item, because the reasoning is what makes the current order defensible.

**Status legend:** `DONE` · `IN PROGRESS` · `NEXT` · `PLANNED` · `DEFERRED` ·
`DROPPED`

| | Milestone | Status |
|---|---|---|
| **R0** | Pasta V1 — evidence-backed comparison over existing records | **DONE** |
| **R1** | Crawl provenance and evidence preservation | **NEXT** (gate on the next crawl) |
| **R2** | Generic validation layer + published extraction contract | PLANNED |
| **R3** | Variation-aware product families | PLANNED |
| **R4** | Amazon.com as a validated marketplace | DEFERRED |
| **R5** | Reviews as an evidence source | DEFERRED |

---

## Decision principles

These are the tie-breakers. When a proposal conflicts with one of them, the
principle wins unless new measurement overrides it.

1. **Product value over scraper sophistication.** Extraction complexity is
   only worth what it changes in a research answer.
2. **Evidence over speculation.** Measured crawl behaviour, real records and
   the corpus test beat assumptions about Amazon.
3. **Correctness over coverage.** A missing value is better than a
   confidently wrong one. `unknown` is a legitimate output.
4. **Preserve evidence.** Never discard source material because the parser
   does not yet understand it.
5. **Avoid unnecessary re-crawling.** Prefer offline interpretation of
   records we already hold.
6. **Keep category logic downstream.** The acquisition layer must never learn
   what "good pasta" means.
7. **Avoid premature marketplace abstraction.** Generalise where commonality
   is observed; adapt where structural difference is measured.
8. **Traceability matters.** Every value and every recommendation must be
   traceable to the source text it came from.

---

## R0 — Pasta V1: evidence-backed comparison over existing records

**Status: DONE** · no crawl required · runs offline over existing JSONL

Shipped as `amazon_scraper/analysis/`, with `tests/test_analysis.py` and the
evidence it was built from in `tests/cases/`.

### Outcome

A user can ask "which of these is better dry pasta, and why?" and get an
answer traceable to the exact source sentence.

### Why this is first

The repository contains no consumer of the extraction output. A contract
cannot be stabilised (R2) and provenance cannot be prioritised (R1) without
one — and measurement shows the current trust semantics are wrong in a way
only a consumer exposes:

- `nutrition.confidence: "high"` records fail plausibility checks **more**
  often than `"medium"` ones — 5/45 vs 2/40 on the 195-record validation set.
  Confidence currently describes the extraction *method*, not the value.
- Price per kg, the axis the whole use case rests on, is silently wrong on at
  least 8 of 163 dry-pasta records. `B08JLSVW3J` (16 × 500 g Garofalo
  Gragnano) reports **€62.56/kg** instead of ≈€3.91/kg; `B0173KFFIG` (12 ×
  500 g Gragnano box) reports **€0.32/kg** instead of ≈€6.47/kg. Both would
  be ejected from any ranking.

### Scope

- Dry-pasta classification from breadcrumbs and the ingredient declaration.
  (The 195-record search output also contains a toilet brush, a cookbook,
  ready meals, chilled pasta and spice blends. Classification is not
  optional.)
- Comparison axes, each carrying the verbatim source quote and its field of
  origin: **price per kg**, **raw material**, **production-method claims**
  (bronze die, slow drying, low-temperature drying), **origin claims** (Italy,
  Gragnano IGP/DOP, Italian wheat), **protein per 100 g**.
- Validation of exactly those axes: package-quantity conflict detection,
  price-per-kg plausibility, nutrition mass balance and Atwater coherence,
  unit-versus-field agreement, and rejection of a matched number that is
  itself part of the basis phrase.
- An explicit `unknown` state, distinct from "absent" and from "conflicting".

### Explicitly out of scope

A general validation framework; a numeric quality score; variation/family
grouping; any change to the spider; any new marketplace; nutrition coverage
work; touching `amazon_search.py`.

### Done when

- [x] Every product is classified or explicitly unclassified.
- [x] Every surfaced price per kg either passes conflict detection or is
      shown as disputed with the conflicting evidence attached.
- [x] The nine known-bad quantity records are each corrected or flagged, and
      none is silently ranked: `B08JLSVW3J`, `B08HQSZR3D`, `B0173KFFIG`,
      `B0BG28G6SZ`, `B0C3WCFKHT`, `B0C5XK2QFR`, `B0BTPZ7TXJ`, `B0CH3MHVF8`,
      `B0GQ5BKHPT`.
- [x] The seven implausible nutrition records are suppressed or marked, never
      presented as fact: `B0C3WCFKHT`, `B089HJPK5T`, `B0FWXQ6NWM`,
      `B0FWXCDCYV`, `B07NZ1K8L3`, `B086K1MFSL`, `B0BP2QDLPQ`.
- [x] A regression test pins each of those cases to the rule that catches it.

> `B0CH3MHVF8` is listed because a crude detector flagged it; the reconciler
> shows it as **corroborated**, not disputed — its 2 500 g total is correct
> ("(1 x 500 g) (Packung mit 5)"). It is in the list as a false-positive
> guard.

### Measured on completion

Over the 195-record Amazon.de validation set:

| | |
|---|---|
| Classified | 161 dry pasta · 34 other · **0 unclassified** |
| Price per kg | 137 trusted · 12 disputed · 5 unverified · 7 unknown |
| Pack quantity | 88 trusted · 12 disputed · 54 unverified · 7 unknown |
| Raw material | 88 trusted (ingredient declaration) · 50 unverified (marketing text) · 23 unknown |
| Protein per 100 g | 52 trusted · 8 disputed · 1 unverified · 6 unknown · 94 not published |
| **Comparable** | **143 of 161** have at least one trusted comparison axis |

Claims found, of 161: made in Italy 62 · bronze die 56 · Gragnano IGP 46 ·
Italian wheat 42 · low-temperature drying 28 · slow drying 22.

Two findings worth carrying forward:

- **Building the consumer changed the rules.** An earlier reconciler disputed
  19 prices; six of those were its own false positives. Multiplying a title's
  pack count by the attribute table's item weight is circular — whether that
  weight is per item or per pack is the question under dispute — and
  `"Packung mit 500g"` read as a fifty-pack because a regex backtracked
  `500` down to `50`. Both are now guarded by named tests. This is the
  argument against promoting these rules to a generic layer (R2) before a
  second category has exercised them.
- **E4 is answered: 143 of 161, far above the 60 threshold.** V1 does not need
  to reframe as an evidence-gap report.

---

## R1 — Crawl provenance and evidence preservation

**Status: NEXT — and this is a gate.** It must land before the next production
crawl, because the evidence it captures cannot be recovered afterwards.

### Outcome

A crawl becomes reproducible and auditable, and future extraction work stops
requiring a re-crawl.

### Scope

- `run_id`, run start time, spider arguments and the **acquisition locale**
  (today implicit in `Accept-Language` in `settings_baseline.py`) written to a
  run manifest and onto every record.
- One discovery-occurrence record per (run, query, search page, position,
  ASIN, sponsored flag, search-result title, search-result price), emitted
  **before** the dedupe check. PDP fetching stays deduplicated; today a repeat
  sighting is dropped before anything is recorded, so the evidence is lost.
- The raw `dimensionValuesDisplayData` / twister blob captured verbatim, with
  no interpretation. It is present on 24 of 35 corpus pages and carries the
  labels that resolve the quantity conflicts R0 can only flag
  (`"500 g (16er Pack)"`).
- Retain fetched PDP HTML — measured at 390 KB gzipped / 2.1 MB raw per page,
  ≈76 MB for a 195-product run.
- Version the product evidence set: `data/` is gitignored, so the corpus this
  roadmap rests on exists on one machine only.

### Explicitly out of scope

Separate entity files or tables for hits versus products; any locale
abstraction layer; any change to pacing, proxying or headers; interpreting the
variation blob.

### Done when

A fresh three-query crawl produces a run manifest, a complete occurrence log
in which one ASIN found under two queries appears twice, a locale field on
every record, and an offline re-extraction from retained HTML with no network
access.

---

## R2 — Generic validation layer + published extraction contract

**Status: PLANNED**

### Outcome

Downstream analyzers — the second category, not just pasta — inherit trust
semantics instead of reinventing them, against a documented, versioned record.

### Scope

- Promote the category-neutral rules proven in R0 (unit/field agreement, mass
  balance, internal source conflict, quantity-versus-price coherence) into a
  generic layer between extraction and category analysis.
- Replace `nutrition.confidence` with value-level semantics: separate *how a
  value was obtained* (`source`) from *whether it survived validation*
  (`status`).
- Publish the schema with a stated compatibility policy; bump
  `SCHEMA_VERSION`.

### Explicitly out of scope

Category-specific rules; rewriting the extractor; coverage work.

### Done when

A second category analyzer consumes the contract without re-deriving trust
rules, and the corpus regression test covers validation output.

---

## R3 — Variation-aware product families

**Status: PLANNED** — blocked on R1 capturing the raw variation blob.

### Outcome

Pack-size variants of one product are compared as a single offer family, and
the "same pasta, sixteen ASINs" distortion disappears from rankings.

### Scope

Interpret the raw blob into a family identity and a pack-size dimension; use
it as an additional quantity-conflict resolver; decide **at this point, and
not before** whether `DiscoveryOccurrence` / `Product` / `OfferFamily` need to
become separately persisted entities.

### Explicitly out of scope

Crawling sibling ASINs that were never discovered.

### Done when

Variants collapse into one comparison row with per-pack price per kg, and
family evidence resolves at least the quantity conflicts R0 could only flag.

---

## R4 — Amazon.com as a validated marketplace

**Status: DEFERRED.** Reconsider when a stated user need for US product
research exists. "Architecturally supported" is already true and costs nothing
to keep.

### Scope when it starts

A `.com` validation crawl from a US IP; the US nutrition parser
(`#nic-nutrition-facts`, reversed and merged cells, per-serving basis) plus
serving-size conversion **with validation attached** — per-serving → per-100 g
is a derivation, and derivations produced the worst values on `.de`; `.com`
price and unit-price re-measurement; delete or validate the speculative
`amazon.co.uk` and `amazon.it` profiles (`amazon.it` currently declares German
as its label language, which would map nothing on Italian pages and emit an
empty `attributes` block beside a full `raw_tables`).

### Done when

`.com` coverage and validation figures are comparable to the `.de` run, and US
nutrition either converts correctly or returns `unknown`.

---

## R5 — Reviews as an evidence source

**Status: DEFERRED**, behind an explicit decision test.

Reviews could settle one thing PDP evidence cannot: whether a pasta holds its
texture and cooking time in practice — i.e. whether a vendor's bronze-die or
slow-drying claim shows up in outcomes.

**Decision test:** after R0, count comparisons that ended in "both products
claim the same thing and nothing distinguishes them". Above ~30%, reviews earn
their crawl-graph expansion.

---

## Deferred and rejected work

| Capability | Decision | Reconsider when |
|---|---|---|
| Browser automation (Playwright, Selenium) | **REJECTED** | `amazon/challenge/*` becomes non-zero at a meaningful rate, or a field with demonstrated product value is found to exist only after JS execution. Today: 201/201 HTTP 200, zero challenges; the one client-loaded structure found duplicates server-rendered data. |
| Proxy rotation, fingerprinting | **REJECTED** | Sustained 429/503 on **PDP** requests under current pacing. The measured 503s were a `/s?` burst artifact, fixed by sequential search pacing. |
| OCR of product / A+ images | **DROPPED** | A named product question is blocked by image-only data. Measured: 0 of 60 bronze-die and 0 of 50 Gragnano claims are A+-image-only. Justifying evidence would be ≥20 records where a **V1 axis** is `unknown` and the value is visible only inside an image. |
| Reviews | **DEFERRED → R5** | The decision test above. |
| Amazon.com completion | **DEFERRED → R4** | A stated user need for US research. |
| Framework / runtime upgrade | **DEFERRED (maintenance)** | A product goal is blocked by the runtime. The last upgrade silently dropped an attribute table from two corpus pages; the corpus test is the gate. Never mix an upgrade with product work. |
| `amazon_search.py` | **DROP — delete** | Never. Dead code with hardcoded `.com` URLs and a documented off-by-one; its presence misleads readers about the architecture. |
| Nutrition coverage beyond validation | **DEFERRED** | Never as a coverage goal. 44% is Amazon's ceiling, not the parser's. |

---

## Product boundaries

| Boundary | Decision |
|---|---|
| Generic extraction | **Correct as is.** No pasta logic in the parser; all fourteen measured pasta signals are recoverable from `raw_tables`, `content.*` and `food.ingredients`. Do not trade "raw first, normalized second" for coverage. |
| Food extraction | **Correct placement**, one change: the food layer must stop asserting values it cannot defend. |
| Validation | **Two layers, never inside extraction.** Extraction stays faithful to the source. *Generic:* unit-versus-field disagreement, basis-phrase-as-value, mass balance, Atwater, quantity-versus-price coherence, on-page source conflict. *Category:* plausibility bands, claim/ingredient contradictions, price floors. |
| Category analysis | **Downstream of the JSONL.** The acquisition layer never learns what good pasta is. |
| Marketplace-specific | `shared structural extraction + marketplace profile + adapters where measured evidence demands`. Correct, but currently over-applied: two profiles exist that nobody validated. |
| Discovery / Product | **Separate the record now (R1), defer the entity (R3).** The requirement is that a repeat sighting must not cost a repeat fetch and must not be erased. |
| Locale | **Record it, do not abstract it.** Justification is correctness: the request locale and the label vocabulary are chosen independently today and can disagree with no error at all. German stays the authoritative Amazon.de discovery locale. |

---

## Open experiments

Questions the repository cannot currently answer. Each blocks a specific
decision; none blocks R0.

### E1 — True package-quantity error rate

- **Blocks:** whether price per kg can remain V1's primary axis.
- **Why unresolved:** conflict detection needs an independent pack hint. After
  R0, 100 of 161 dry-pasta records carry one (88 corroborated, 12 disputed);
  the other 61 are unverified or unknown and could hide errors of the same
  kind. The 12 found are a floor, not the rate.
- **Experiment:** hand-verify extracted total quantity against the live PDP
  for a random 30 of the 163 records. Half a day, no crawl changes.
- **Threshold:** >15% wrong or unresolvable → price per kg cannot be a trusted
  axis; V1 leads with raw material and claim evidence, and R3 is pulled
  forward.

### E2 — Cross-query discovery overlap

- **Blocks:** whether the SearchHit/Product entity split belongs in R1 rather
  than R3.
- **Why unresolved:** dedupe happens before anything is recorded. Position-gap
  analysis hints the overlap is small (12 gaps on the first query, which
  cannot have cross-query dedupe, versus 15–16 on later ones) but cannot
  measure it.
- **Experiment:** re-run the same three queries with
  `max_products_per_query=0`, logging every (query, page, position, ASIN)
  before dedupe. ≈20 minutes of crawl.
- **Threshold:** >10% repeat sightings → the entity split moves into R1.

### E3 — Discovery coverage of the category

- **Blocks:** whether query design becomes a roadmap item ahead of R2.
- **Experiment:** run the R0 classifier over the 163 records and count
  distinct producers with bronze-die claims against a manual list of ~15 known
  quality Italian producers. Zero crawl cost.
- **Threshold:** fewer than half the known producers appear → discovery, not
  extraction, is the bottleneck.

### E4 — Does the trust bar leave enough to compare?

- **Blocks:** the framing of V1 itself.
- **Experiment:** measured inside R0 — count products with at least one
  trusted comparison axis.
- **Threshold:** <60 of 163 comparable → V1 reframes to "here is what Amazon
  does and does not tell you about these products", and evidence-gap
  reporting becomes the user-visible feature.

---

## Superseded hypothesis (P0–P6)

Kept for the reasoning, not as a plan.

| Item | Verdict | Became | Rationale |
|---|---|---|---|
| P0 stabilise generic extraction contract | **CHANGE** | R2 | Already pinned by `SCHEMA_VERSION`, the schema table in EXTRACTION.md and the 35-page corpus test. What was missing is a consumer. Freezing first would have ratified `confidence` semantics that measurement shows are inverted. |
| P1 improve discovery/product modelling | **SPLIT** | R1 (additive provenance) / R3 (entity separation) | Recording occurrences is cheap and irreversible if skipped. Promoting them to separate entities is a storage decision with no consumer demanding it. |
| P2 add validation / trust layer | **MERGE** | R0 (axis-specific) + R2 (generic) | Validation is a precondition for an honest first ranking, but a general framework with no consumer repeats P0's mistake. |
| P3 build dry-pasta analysis | **MOVE_EARLIER** | R0 | The only item producing user value, and it needs no crawl. |
| P4 product variations / twisters | **SPLIT** | R1 (raw capture) / R3 (family modelling) | The twister blob is validation evidence first and a grouping feature second. |
| P5 validate / complete Amazon.com | **DEFER** | R4 | No product need; `.de` has produced no user-facing output yet, and the unvalidated `.co.uk`/`.it` profiles are already the debt this creates. |
| P6 optional enrichment (OCR, reviews) | **SPLIT** | OCR dropped / reviews R5 | A+ content contributes zero unique evidence for V1's top claims. |
