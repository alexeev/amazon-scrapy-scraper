# Product roadmap

The plan of record for this repository. It supersedes the P0–P6 hypothesis
that preceded it; that hypothesis is kept below, with the verdict on each
item, because the reasoning is what makes the current order defensible.

**Status legend:** `DONE` · `IN PROGRESS` · `NEXT` · `PLANNED` · `DEFERRED` ·
`DROPPED`

| | Milestone | Status |
|---|---|---|
| **R0** | Pasta V1 — evidence-backed comparison over existing records | **DONE** |
| **R1** | Crawl provenance and evidence preservation | **DONE** |
| **R2** | Generic validation layer + published extraction contract | **DONE** |
| **R3** | Variation-aware product families | **DONE** (one criterion unmet — see below) |
| **R4** | Amazon.com as a validated marketplace | DEFERRED |
| **R5** | Reviews as an evidence source | **DONE** (cost estimate was wrong — see below) |
| **R6** | A command line for the things every category needs | **NEXT** |
| **R7** | Attributed search: finding a claim vs crediting it | PLANNED |
| **R8** | Marketplace-aware text matching | PLANNED |
| **R9** | A second pass for missing prices | PLANNED (behind a decision test) |
| **R10** | Scoring as a shared facility | **DEFERRED** — one consumer is not two |

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

**Status: DONE.** It was a gate on the next production crawl, and it landed
before one ran.

Shipped as `amazon_scraper/run.py` plus the spider wiring, with
`tests/test_run.py` and the first saved search page in
`tests/corpus/amazon_de_search/`.

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

- [x] A fresh three-query crawl produces a run manifest.
- [x] A complete occurrence log in which one ASIN found under two queries
      appears twice.
- [x] A locale field on every record.
- [x] An offline re-extraction from retained HTML with no network access.

### Measured on completion

Verification crawl: 3 queries, 1 search page each, 10 products per query,
Amazon.de, no proxy. 34 requests, 34 × HTTP 200, 0 retries, 0 challenges,
`finish_reason: finished`.

| | |
|---|---|
| Discovery occurrences | **213**, of **170** distinct ASINs |
| Repeat sightings | **43 (20% of occurrences)** — 21 same-query pairs, 12 ASINs under more than one query |
| Sponsored placements | **69 of 213 (32%)** of what a shopper is shown |
| Outside the result grid | 33 of 213 (carousels and ad slots) |
| PDPs fetched | 30 — fetching stayed de-duplicated |
| Records with `run_id` and `locale` | 30/30 |
| Pages retained | 30, 11.6 MB gzipped (≈387 KB each, as estimated) |
| Offline re-extraction | **30/30 identical**, no network |
| Variation matrix captured | 16/30 records; 24/34 corpus pages |

Three findings worth carrying forward:

- **A latent locale bug was already in the repository.** Scrapy ships
  `Accept-Language: en` by default and the non-baseline settings profile never
  overrode it, so every Amazon.de crawl on that profile asked Amazon for
  English while reading the answer with German label lists. Nothing failed;
  records would simply have carried an empty `attributes` block beside a full
  `raw_tables`. The gate now refuses to start, with a message naming the fix.
  Only the validated baseline profile was ever correct, and by accident of
  having been written for amazon.de.
- **The discovery selector was never the result list.** On a live search page
  it matches 82 nodes, of which 60 are the result grid and 22 are carousels
  and ad slots — 12 of those with an empty `data-asin`. That is why position 1
  was missing from every query in the last validation run. Discovery
  behaviour is unchanged; both the raw index and the grid rank are now
  recorded, and the grid rank is the one that means anything.
- **A third of placements are advertising.** Not actionable yet, but it is the
  kind of fact that changes what "what does Amazon show for this query" means,
  and it was previously unrecordable.

---

## R2 — Generic validation layer + published extraction contract

**Status: DONE.** The hold is released: the milestone's premise was that a
rule earns promotion once a *second* consumer has exercised it, and this
milestone built the second consumer first and promoted afterwards.

Shipped as `amazon_scraper/validation/` and `amazon_scraper/analysis/
categories/`, with **[CONTRACT.md](CONTRACT.md)**, `tests/test_validation.py`,
`tests/test_mounting_paste.py`, a validation snapshot in the corpus test, and
the crawl it was measured on in `data/evidence/`.

### Outcome

Downstream analyzers — the second category, not just pasta — inherit trust
semantics instead of reinventing them, against a documented, versioned record.

### The second category

Tyre mounting paste for a 10-inch pneumatic scooter tyre with an inner tube,
on an aluminium rim. Chosen because it shares almost nothing with dry pasta:
non-food, no nutrition, sold in tubs, tubes, bottles and aerosols, filed by
Amazon under four unrelated departments, and judged on criteria that are not
numeric at all — the paste must *dry after mounting and stop lubricating*, be
safe on rubber, and be free of mineral oil.

Its economics invert too. Pack size is not a discount axis: one scooter tyre
needs a few grams, the shelf is five-kilogram workshop tubs, and the cheapest
paste per kilogram is the worst buy. So it ranks on **smallest pack first**
and refuses price per kilogram as a ranking while still showing it.

### Scope

- Promote the category-neutral rules proven in R0 into a generic layer between
  extraction and category analysis — **done**, as `validation/`, which now
  also owns the *ordering* (`detect → category bands → resolve → promote`)
  that was previously a comment inside the pasta module.
- Replace `nutrition.confidence` with value-level semantics: separate `source`
  from `status` — **done**, schema v4.
- Publish the schema with a stated compatibility policy; bump
  `SCHEMA_VERSION` — **done**, CONTRACT.md, schema v4 / contract v1.

### Done when

- [x] A second category analyzer consumes the contract without re-deriving
      trust rules. Asserted mechanically, not by inspection:
      `tests/test_mounting_paste.py` parses the module's imports and fails if
      it reaches past the contract into `validation.quantity`,
      `validation.pricing` or `validation.nutrition`.
- [x] The corpus regression test covers validation output — a second snapshot,
      `validated.jsonl.gz`, over all 39 saved pages, produced with **no**
      category profile so that what is pinned is the layer belonging to nobody.

### Measured on completion

Second-category crawl: 3 queries, 1 search page each, 30 products per query,
Amazon.de, no proxy. 93 requests, 93 × HTTP 200, 0 retries, 0 challenges,
`finish_reason: finished`. 90 records.

| | dry pasta (195 records) | tyre mounting paste (90 records) |
|---|---|---|
| Classified | 165 · 30 other · **0 unclassified** | 43 · 47 other · **0 unclassified** |
| Pack quantity | 131 trusted · 13 disputed · 14 unverified · 7 unknown | 25 trusted · 1 disputed · 6 unverified · 11 unknown |
| Price per base unit | 100 trusted · 9 disputed · 2 unverified · 54 unknown | 13 trusted · 1 disputed · 1 unverified · 28 unknown |
| **At least one trusted axis** | **117 of 165** | **32 of 43** |

Effect on dry pasta of the two rules the second category forced — same
records, same code path:

| | before | after |
|---|---:|---:|
| Pack quantity trusted | 108 | **131** |
| Pack quantity unverified | 37 | **14** |
| Pack quantity disputed / unknown | 13 / 7 | 13 / 7 *(identical)* |
| Price per base unit trusted | 100 | 100 *(identical)* |
| Protein trusted | 61 | 60 |

Five findings worth carrying forward.

- **Three of the four things the layer had to learn were bugs, not
  generalisations.** The plan assumed promotion would be mostly a move. What
  the second category actually produced was: a price-per-unit path hard-wired
  to kilograms that silently discarded Amazon's own figure whenever it was
  quoted per litre; an extraction bug reporting a 50 ml tin as 50 g, because
  `total_quantity_unit` was inferred from any volume field on the page rather
  than from the row the total came from; and a missing generic rule that would
  have let a *trusted* "100 g of fat per 100 g" through. None of these were
  visible with one consumer, and none of them is category-specific. That is
  the argument R2 was waiting for, and it came out stronger than expected.
- **The missing rule is the cleanest measurement in this repository.**
  German *Fett* means grease as well as fat, so `"Fett wird in einer 100 g
  Tube geliefert"` on bicycle grease parses as a nutrition declaration — with
  the per-100 g basis apparently confirmed. Dry pasta was protected only by
  having a plausibility band. The rule that was missing is category-neutral:
  a declaration carrying a single nutrient has nothing on the page to confirm
  it, so it may be shown and never trusted. **Thirteen lone-nutrient blocks
  exist across the two validation sets and all thirteen are artefacts of
  matching a word** — nine in dry pasta, six of them reporting 100 g of
  protein per 100 g and one reporting 534.
- **R0's refusal to read a bare title weight was right, and too broad.** The
  reasoning was multipacks: `"Garofalo Fusilli 500g"` on a sixteen-pack states
  the weight of one box. Take the multipack away and the ambiguity goes with
  it. Mounting paste does not use multipack phrasing at all — it writes
  `"Reifenmontagepaste 5 kg"` and means it — and only 2 of 43 pastes had a
  confirmable pack size. The rule added is narrow and **asymmetric**: when
  nothing on the page claims more than one unit, a bare weight in the
  listing's own text may *confirm* the attribute total and may never
  contradict it. On dry pasta it moves 23 records from unverified to trusted
  and leaves every disputed and every unknown exactly as it was.
- **A profile is data, and that had to be enforced rather than intended.**
  The first draft let a category pass a callable. The version that shipped
  accepts plausibility bands and a label, and nothing else, because the
  ordering the bands participate in is the part a second category has no way
  to know is load-bearing. `price_band=None` is a legitimate answer: mounting
  paste spans 50 ml tubes and 5 kg tubs two orders of magnitude apart per
  kilogram, and inventing a band to have one would reject real listings.
- **The category answer is an evidence-gap report, and honestly so.** The
  criterion that decides this purchase — does the paste dry out and stop
  lubricating — is stated on **3 of 43 listings**. "Free of mineral oil" and
  "solvent-free" are claimed by **none**. Water-solubility, the usable proxy,
  appears on 6. One listing declares a mineral-oil base, which is the only
  *disqualifying* evidence on the page and is surfaced as an adverse claim.
  A ranking that did not say this would be inventing confidence.

### What the second category could not fix

`price_per_base` is `unknown` on 28 of 43 mounting pastes, because 23 have no
price at all — no purchasable offer at crawl time, the same volatility R3
measured on the pasta set. Not an extraction gap and not fixable downstream.

### Retired from scope

Nothing. The one thing deliberately not built is a `nutrition: bool` flag on
the profile: a non-food record has no food block, the nutrition rules cost it
nothing, and adding a switch would have been a category telling the generic
layer which rules to run — exactly what the profile is shaped to prevent.

---

## R3 — Variation-aware product families

**Status: DONE**, with one of its two completion criteria **not met** and the
reason recorded rather than worked around.

Shipped as `amazon_scraper/analysis/variation.py` plus the reconciler and
report wiring, with `tests/test_variation.py`.

### Outcome

Pack-size variants of one product are compared as a single offer family, and
the "same pasta, sixteen ASINs" distortion disappears from rankings.

### Scope

Interpret the variation blob R1 now captures into a family identity and a
pack-size dimension, and use it as an additional quantity-conflict resolver —
`"500 g (16er Pack)"` is the independent statement that settles the disputes
R0 can only flag.

Also the part of the discovery model R1 deliberately left alone: occurrences
are now persisted separately from products, but nothing *joins* them. Build
that join when there is a consumer for it, and not before.

### Explicitly out of scope

Crawling sibling ASINs that were never discovered.

### Done when

- [x] Variants collapse into one comparison row with per-pack price per kg.
- [ ] **Not met:** family evidence resolves at least the quantity conflicts R0
      could only flag. Seven of R0's eight flagged ASINs reappeared in the
      verification crawl and **none of them has a variation matrix at all**.
      The evidence this milestone was meant to apply does not exist on those
      pages. No amount of further work on variations changes that, so the
      criterion is retired rather than chased.

### Measured on completion

Re-ran the original three-query validation crawl under schema v3: 195 records,
201 requests, 201 × HTTP 200, 0 retries, 0 challenges, `finished`.

| | |
|---|---|
| Variation matrix present | **68/195 (35%)** |
| Dry pastas → offers | 165 listings → **159 offers**; 6 offers hold more than one crawled pack size |
| Pack quantity improved | **22 unverified → trusted**, **2 unverified → disputed** (24 records, 12%) |
| Only pack-size label on the page | 26 records |
| R0's flagged conflicts resolved | **0 of 7** — none carries a matrix |

Four findings.

- **The corpus overstated how common variation data is, and I had used that
  figure to justify this milestone.** "Present on 24 of 35 corpus pages" is
  71%; on records from an ordinary search crawl it is **35%**. The corpus
  pages were chosen for layout diversity, which is exactly the bias that makes
  them a bad basis for a frequency claim. Checked against the retained pages,
  not assumed: where the matrix is missing it is genuinely absent from the
  HTML, not missed by the extractor.
- **The premise in the original review was wrong.** "Sixteen ASINs of the same
  Garofalo pasta crowd the ranking" — those listings are different *shapes*
  under one parent, not pack sizes. Amazon files spaghetti, penne and fusilli
  under a single family, so collapsing by family would have merged different
  products. Grouping is by size dimension only, and the corpus proves that is
  necessary rather than fastidious.
- **The real payoff was the quantity side, not the comparison side.** One case
  matters on its own: `B0DM21MLWV` (Barilla Integrale) was shown by R0 at
  **€38.56/kg** as an unverified but plausible price, because Amazon's
  attribute table says 1 kg and its own unit price is quoted *per piece*. The
  variation matrix says `10kg`. The real price is **€3.86/kg** — a tenfold
  error on a flagship brand, invisible to every source R0 had.
- **Price coverage is volatile between crawls.** The September run had a price
  on 195/195 records; this one on 141/195. Investigated rather than assumed:
  no price payload keyed to the main ASIN exists anywhere in those responses,
  and the discovery log shows search did not price them either. They had no
  purchasable offer at crawl time. The extractor is right to return nothing,
  and §1.4's finding — that no high-value field needs browser execution —
  still holds.

### Retired from scope

The discovery/product *join* stays unbuilt. R1 persists occurrences separately
and nothing reads them yet; this milestone did not create a reader, so the
reasoning that put R0 ahead of P0 applies unchanged — do not model what
nothing consumes.

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

**Status: DONE.** The decision test passed decisively, and the milestone cost
roughly a tenth of what this entry budgeted, for a reason worth recording.

Shipped as `amazon_scraper/extraction/reviews.py` and
`amazon_scraper/validation/reviews.py`, with `tests/test_reviews.py` (33 tests)
and schema v5. Driven by the third category, basmati rice, where the properties
that decide the purchase — does it smell of basmati, does it arrive with moths
in it — are stated nowhere except in reviews.

### The decision test, run

Threshold was ~30% of comparisons ending in "both claim the same thing and
nothing distinguishes them". On 239 basmati listings: **137 (57%) claim
"extra long", 104 (44%) claim a growing region**, and outside price per
kilogram almost nothing on the page separates them. Far over the bar.

### Why the estimate was wrong, and in which direction

This entry priced reviews as **"crawl-graph expansion"** — following
`/product-reviews/` pagination. That was wrong twice:

- **The data was already in hand.** Eight to thirteen review cards and the
  complete ratings histogram are in the PDP HTML the crawler has retained
  since R1. **Zero additional requests**, and both production crawls were
  re-extracted offline to get them.
- **The expensive version is not available at any price.**
  `/product-reviews/<ASIN>` redirects to sign-in. The PDP widget is the only
  review evidence reachable without an account, so there is no larger version
  of this milestone to come back for. Recorded here so nobody re-scopes it.

### What the two structures are, and why they are not interchangeable

| | histogram | rendered sample |
|---|---|---|
| Covers | **every rating the listing ever received** | 8–13 cards Amazon selected |
| Carries | five percentages | the words |
| Sums to 100 | **38 of 38 corpus pages** | — |
| Reconstructs the published average | **within 0.08 stars, worst case** | — |
| May support a rate | **yes** | **never** |

Because the histogram is an independent statement of the same fact the average
asserts, it promotes the average from `unverified` to `trusted` under the
layer's existing corroboration rule — no new rule was needed. And because the
sample is a sample of Amazon's choosing, a complaint found in it establishes
**presence, never frequency**, which the Value says in its own notes.

### The vocabulary needed no extension, and that is the result

The category needed `not_claimed` and `unknown` to mean opposite things for
the same missing sentence:

- a **vendor** controls the whole page, so an absent claim is `not_claimed`;
- **buyers** control nothing — Amazon picked which 13 of 3 446 reviews to
  render — so an absent complaint is `unknown`.

R2's vocabulary already expressed that. Nothing was added to it.

### Measured on completion

| | |
|---|---|
| Corpus pages carrying a review block | **38 of 39** |
| Pages carrying a histogram | **38** |
| Review cards extracted | **277** |
| Written on *another* marketplace | **82 (30%)** — machine-translated onto the page |
| Carrying a variant label | 201 |
| Marked verified purchase | 271 |
| Schema v4 → v5 | **purely additive**; corpus diff touched only `reviews.*` and `blocks_present` |

Three findings worth carrying forward.

- **30% of the "reviews" on an amazon.de page were not written for
  amazon.de.** They are real, and they are about a different importer, a
  different batch and occasionally a different product. Counted apart rather
  than dropped.
- **Amazon pools reviews across pack sizes, and the page says so if you
  read the format strip.** Tilda Pure Original's 10 kg listing shows reviews
  from three pack sizes. This was previously invisible; it is now a flag on
  the value.
- **Splitting the search by star rating was not a refinement, it was
  required.** Searching all reviews for stickiness complaints matches "die
  Körner kleben überhaupt nicht" — a five-star endorsement — and it was the
  single commonest false positive in the category. Positive signals are now
  searched in 4–5★ reviews and negative ones in 1–2★, pinned by test.

---

## R6 — A command line for the things every category needs

**Status: NEXT.** The cheapest item on this roadmap and the best evidenced:
four scripts were written and thrown away in the course of one research
question. Nothing new is needed, only exposing capability that already exists.

```
amazon_scraper.run reextract <run_dir> [--feed old.jsonl] -o new.jsonl
amazon_scraper.analysis <cmd> feed1.jsonl feed2.jsonl ...   # merge by ASIN
amazon_scraper.analysis shortlist <feeds> --category X --limit N
amazon_scraper.analysis cards <feeds> ASIN ASIN ASIN
```

Offline re-extraction is currently documented in README.md **as a code
sample** — proof that it works, and a sign that it should be a command. The
analysis CLI takes exactly one feed path, so a two-crawl study needs a
merge-by-ASIN loop the user writes themselves.

### Done when

A basmati shortlist of the kind described in [reports/](reports/README.md)
reproduces from shipped commands, with no scratch scripts.

---

## R7 — Attributed search: finding a claim vs crediting it

**Status: PLANNED.** Two categories have now independently hit the same bug:
text on an Amazon page is not necessarily *about the product the page sells*.

Measured on basmati: searching every text field for the milling degree marked
**53 of 239** records parboiled and **29 were wrong** — cross-sell copy ("Neben
unseren PURE BASMATI Reis haben wir auch bereits vorgekochte …", which marked
the Stiftung Warentest winner as parboiled), A+ comparison tables listing a
brand's entire shelf, recipe suggestions, and the outright negation
"Non-parboiled for authentic basmati". Restricting to title, ingredient
declaration and attribute rows took it to **0**.

Mounting paste hit the same class of error and solved it positionally, in its
own module. That is the second occurrence R2's promotion rule waits for.

### Scope

- `search(..., scope='self' | 'page')` in the validation layer. `self` is the
  fields in which the listing describes its own contents; `page` is
  everything, which is right for *discovering* a claim and wrong for
  *attributing* one.
- Negation-aware matching, so "mineralölfrei" and "Non-parboiled" stop
  registering as declarations of what they deny. Mounting paste needs this at
  least as much as basmati: its entire claim set is "free of X".
- Extend it to external evidence: a listing that names another brand's product
  in its title must not inherit that brand's laboratory result. A real case —
  "Tilda Pure Original Basmati Reis (4 x 2kg)", filed under brand **Kajal**,
  manufacturer **Kajal GMBH**, in a pack size Tilda does not sell.

### Done when

Both existing categories re-run over their saved corpora with no true positive
lost and the known false ones gone, pinned by test.

---

## R8 — Marketplace-aware text matching

**Status: PLANNED.** `\bword\b` is not a safe default on a compounding
language.

German compounds the noun: **"Basmatireis" is one word**, and `\bbasmati\b`
does not match it. Cost, measured: **36 of 239 listings (15%) silently
classified out**, including `AKASH Basmatireis 1 × 10 kg` — one of only two
basmatis Stiftung Warentest rated "gut" in 5/2026, and the cheaper of the two.

Nothing failed and nothing looked wrong: a wrongly rejected product is filed
confidently as `other`, and the summary kept reporting `0 unclassified`. **That
line reads as a health metric and is not one.**

### Scope

A `Marketplace.word(stem)` helper emitting `\bstem` for German and
`\bstem\b` for English, so the decision sits beside the other locale
decisions instead of in every category's regexes. Plus an honest name for the
`0 unclassified` line, which measures only that the classifier reached a
verdict.

---

## R9 — A second pass for missing prices

**Status: PLANNED**, behind a decision test.

**73 of 239 basmati (31%) had no purchasable offer at crawl time** — among them
Rapunzel, Spielberger demeter and two Tilda Pure Original pack sizes. R3
measured the same volatility on pasta (195/195 priced in one run, 141/195 in
the next) and correctly concluded the extractor is right to return nothing.

The product consequence was never drawn: **a study built from one crawl
silently omits a third of its category**, and the omission is invisible in the
output.

### Decision test, before building anything

Re-fetch the 73 unpriced basmati ASINs once, some hours later, and count how
many price. **Below ~30% recovered**, those listings are genuinely dormant and
an automated second pass is not worth its complexity.

---

## R10 — Scoring as a shared facility

**Status: DEFERRED — deliberately, and the reasoning is the point.**

Basmati needed a composite score; `report.py` refuses to offer one, and its
stated reason is right: a score "could not answer why A is better than B".
Three properties made one defensible anyway, and all three look general:

- every component published with its evidence, never just the total;
- a missing input scores **neutral**, never zero — absence of data is not an
  adverse finding;
- the total is **shrunk toward neutral in proportion to how much is unknown**,
  so a listing whose entire case is its own adjectives cannot outrank one with
  an independent measurement.

The third is not theory. The first draft ranked first a 10 kg bag with **five
ratings** whose feature bullet claimed every heavy metal was below the limit of
detection — a sentence no reader can check, scored as though it were a test
report.

But one category is one data point, and this repository's own experience says
promotion before a second consumer produces bugs dressed as generalisations —
in R2, three of the four things the layer "had to learn" were bugs. Dry pasta
and mounting paste both refuse to score, so there is no second consumer asking.
It stays in `basmati_rice.py`.

---

## Deferred and rejected work

| Capability | Decision | Reconsider when |
|---|---|---|
| Browser automation (Playwright, Selenium) | **REJECTED** | `amazon/challenge/*` becomes non-zero at a meaningful rate, or a field with demonstrated product value is found to exist only after JS execution. Today: 201/201 HTTP 200, zero challenges; the one client-loaded structure found duplicates server-rendered data. |
| Proxy rotation, fingerprinting | **REJECTED** | Sustained 429/503 on **PDP** requests under current pacing. The measured 503s were a `/s?` burst artifact, fixed by sequential search pacing. |
| OCR of product / A+ images | **DROPPED** | A named product question is blocked by image-only data. Measured: 0 of 60 bronze-die and 0 of 50 Gragnano claims are A+-image-only. Justifying evidence would be ≥20 records where a **V1 axis** is `unknown` and the value is visible only inside an image. |
| Reviews | **DONE → R5** | Decision test passed at 57% against a 30% bar. Cost a tenth of the estimate: the data is in the retained PDP HTML, and the larger version is unavailable — `/product-reviews/` needs an account. |
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
| Validation | **Two layers, never inside extraction** — shipped in R2 as `amazon_scraper/validation/`, published as [CONTRACT.md](CONTRACT.md). Extraction stays faithful to the source. *Generic:* unit-versus-field disagreement, basis-phrase-as-value, mass balance, Atwater, single-nutrient corroboration, quantity-versus-price coherence, on-page source conflict. *Category:* plausibility bands, claim/ingredient contradictions, price floors — supplied to the generic layer as **data**, never as procedure. |
| Category analysis | **Downstream of the JSONL.** The acquisition layer never learns what good pasta is. Confirmed by a second category in R2: tyre mounting paste needed no change to the crawler, the extractor, or any trust rule — only a profile, a classifier and a list of claims. |
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

### E2 — Cross-query discovery overlap — **RESOLVED**

**43 of 213 sightings (20%) are repeats**, against a threshold of 10%. The
earlier position-gap estimate was too low, because it could only see
cross-query repeats and missed the larger source: the same ASIN listed twice
on one page, once organic and once sponsored.

Over the threshold, so the persistence split moved into R1 and is done —
occurrences live in `discovery.jsonl` and are never collapsed, products live
in the feed. What stays in R3 is the part with no consumer yet: a model that
*joins* them, and offer families. The reasoning is the same one that put R0
before R2 — do not model what nothing reads.

### E3 — Discovery coverage of the category

- **Blocks:** whether query design becomes a roadmap item of its own.
- **Sharpened by R2.** On the mounting-paste crawl, 47 of 90 results were not
  the product searched for, and the *criterion that decides the purchase* is
  stated on 3 of the 43 that were. Whether that is a discovery problem (the
  right products exist and these queries do not surface them) or a category
  ceiling (Amazon listings simply do not say) is now the more interesting
  version of this question, and it is answerable with a hand check.
- **Answered in part by R5's category, and the answer is "discovery".** Eight
  generic queries in German and English, two result pages each, **never
  surfaced AKASH at all** — the brand took a query naming it. AKASH
  Basmatireis is one of only two basmatis Stiftung Warentest rated "gut" in
  5/2026. A researcher who did not already know that result would not have
  reached the product it recommends.
- **The sharper question now:** generic queries systematically under-sample
  **diaspora brands**, which on Amazon.de are a large share of the real shelf
  in exactly the categories where they matter — rice, pulses, spices, flour.
  That is a query-design problem and it is not solved by crawling deeper: the
  broad sweep already went two pages deep per query.
- **Experiment:** for a category, take the brands that only brand-specific
  queries discovered, and measure their share of the final shortlist. On
  basmati: **1 of 8 finalists, and 2 of the 3 products with external
  laboratory evidence.**
- **Threshold:** brand-only-discovered products taking more than ~20% of a
  shortlist → query design becomes a roadmap item, most likely as a
  brand-expansion pass seeded from the first crawl's own brand field.

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
