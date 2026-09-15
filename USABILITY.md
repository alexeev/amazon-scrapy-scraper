# Using this platform for a real research question — what worked, what cost time

Written immediately after answering one: *"find the best dry basmati rice on
Amazon.de for regular home use"*, start to finish, on a repository that had
never seen a grain of rice. Everything below is a measurement or a thing that
actually happened, not a design opinion.

## The headline

**The layering held.** Adding basmati as a third category needed **zero
changes** to the crawler, the extractor's page logic, or any trust rule. The
claim R2 made — "adding a category is one module" — survived a category that is
structurally unlike both of the first two: decided by three different kinds of
evidence at once, with its most important criterion (contaminants) not on the
Amazon page at all.

**The one thing that did need building was reviews**, and that was a roadmap
decision (R5, deferred) rather than an architecture failure. It cost ~480 lines
across two layers and slotted into the existing seams without forcing a change
anywhere else. Schema v4 → v5 was purely additive: the corpus regression test
reported diffs in exactly two places, `reviews.*` and `extraction.blocks_present`,
and nothing else moved.

| | |
|---|---|
| Crawls | 2 · 28 queries · **537 requests, 537 × HTTP 200, 0 challenges, 0 retries** |
| Wall time crawling | 40 min (both runs, sequential, ~14 pages/min) |
| Records | 359 unique ASINs · 239 classified as basmati · **0 unclassified** |
| Pages retained | 501, 181 MB gzipped |
| New code | 1 541 lines across 3 modules |
| New tests | 798 lines, 74 tests · suite went 165 → 239, all green |
| Re-crawls needed after changing the extractor | **0** |

That last row is the one that matters most and is worth stating plainly: the
review extractor **did not exist** when the first crawl started. It was written
while the crawl ran, and both runs were re-extracted offline from retained
HTML. Principle 5 ("avoid unnecessary re-crawling") paid for R1 in a single
afternoon.

---

## What worked, specifically

**1. Evidence-carrying values changed the answer, not just the presentation.**
The basmati question has a health component that is almost entirely unknowable
from Amazon. A system that returned bare numbers would have had to either
invent confidence or drop the component. Because every value arrives with
`status` and a quote, the honest answer — *"3 of 239 sellers claim any lab
testing and none publishes a report"* — is a **result** rather than a gap in
the tooling.

**2. `not_claimed` vs `unknown` turned out to be the load-bearing
distinction**, and the new category needed *both*, in opposite directions:

- A **vendor** controls the whole page, so a claim absent from it is
  `not_claimed` — weak evidence, but evidence.
- **Buyers** control nothing: Amazon picks which 8–13 of 3 446 reviews to
  render. So a complaint absent from that sample is `unknown`, full stop.

That asymmetry was already expressible in the R2 vocabulary. Nothing had to be
added to say it.

**3. The corpus regression test caught the schema bump immediately** and, more
usefully, proved the change was additive before I had to argue that it was.
`python tests/test_corpus.py --update` plus reading the diff took two minutes.

**4. Offer grouping was quietly correct.** 239 listings collapsed to 190
offers. Without it, the shortlist would have been Tilda in five pack sizes.

**5. The plausibility band caught real arithmetic.** 6 disputed prices per kg
out of 239, each a pack-size error rather than a cheap product.

---

## What cost time, in the order it hurt

### 1. Reviews were the whole question, and they were deferred

R5's decision test was *"after R0, count comparisons that ended in 'both
products claim the same thing and nothing distinguishes them'. Above ~30%,
reviews earn their crawl-graph expansion."*

For basmati the figure is far above 30%. **137 of 239 listings (57%) claim
"extra long"; 104 claim a growing region; nothing on the page separates most of
them at all.** The decisive properties — does it smell of basmati, does it
arrive with moths in it — appear *only* in reviews.

Two things about that test, now that it has been run:

- **It was the right test and it was pointed at the wrong layer.** It asked
  whether reviews add evidence to a *comparison*. What reviews actually added
  here was an evidence class with different trust semantics, which is a
  contract question, not a crawl-graph question.
- **The cost estimate was wrong by an order of magnitude.** R5 assumed reviews
  meant "crawl-graph expansion" — following `/product-reviews/` pagination.
  They did not: **8–13 reviews and the complete ratings histogram are already
  in the PDP HTML the crawler has been retaining since R1.** Zero extra
  requests. The expensive version is also impossible — `/product-reviews/<ASIN>`
  redirects to sign-in, so the widget is the only review data reachable
  without an account.

So R5 was priced as a crawl project and delivered as a parsing project. **The
histogram in particular was free and is the single most decision-relevant
number added**: it is complete (not a sample), it sums to exactly 100 on all 38
corpus pages, and it reconstructs Amazon's published average to within 0.08
stars — which makes it an independent corroborating source under the layer's
existing promotion rule.

### 2. Four things had no CLI and became throwaway scripts

Each of these is a thing any future category will need on day one. All four
were written in the scratchpad and thrown away, which is the smell.

| What I needed | What exists | What I wrote |
|---|---|---|
| Re-extract a finished run offline | `run.stored_pages()` + a documented 6-line loop in the README | a 45-line script |
| Analyse several feeds together | the CLI takes exactly one path | a merge-by-ASIN loop |
| Rank by the category's own composite, not one axis | `rank` does one axis | a 60-line ranking script |
| Dump N products' evidence side by side | `card` does one, `compare` does two | a 50-line dump |

The README documents offline re-extraction *as a code sample*. That is a good
sign that it works and a bad sign that it is not a command.

### 3. German compounding broke a classifier, silently

`\bbasmati\b` does not match **`Basmatireis`**, because German compounds the
noun. Cost: **36 of 239 listings (15%) classified out**, among them `AKASH
Basmatireis 1 × 10 kg` — one of only two basmatis Stiftung Warentest rated
"gut", and the cheaper of the pair.

Nothing failed. Classification reported `0 unclassified` throughout, because a
wrongly rejected product is confidently filed as `other`. The existing summary
line *"0 unclassified"* reads as a health metric and is not one.

### 4. Claim searches read text that is about a different product

Searching all text fields for the milling degree marked **53 of 239** records
parboiled. **29 were wrong**, in four distinct ways:

- **cross-sell copy** — Tilda's own bullet advertises its steamed range inside
  the page of a rice that is not steamed, which marked the Stiftung Warentest
  winner as parboiled;
- **A+ comparison tables** listing a brand's whole shelf, sella lines included;
- **recipe suggestions** ("can be used for Biryani, Pulao, Steamed Rice");
- **negation** — "Non-parboiled for authentic basmati" read as a parboiled
  declaration.

Restricting to title + ingredient declaration + attribute rows took it to
**0 wrong**. This is not a basmati problem. `text_fields()` deliberately walks
everything, which is right for *finding* a claim and wrong for *attributing*
one, and every category will rediscover this. Mounting paste already hit the
same class of bug and solved it positionally, inside its own module.

### 5. A reseller can inherit somebody else's laboratory result

`Tilda Pure Original Basmati Reis, 1er Pack (4 x 2kg)` is filed under brand
**Kajal**, manufacturer **Kajal GMBH**, ingredients "Basmatireis tilda", in a
pack size Tilda does not sell. Matching external evidence on the title alone
handed it a Stiftung Warentest result. Requiring the brand *or* manufacturer
field to agree fixed it.

Worth generalising: **`brand` is the seller's brand field, not the product's
manufacturer.** On this crawl the two disagree often enough to matter, and
`attributes.manufacturer` is frequently the more truthful of the two.

### 6. A third of the shelf had no price

**73 of 239 basmati (31%) had no purchasable offer at crawl time**, including
Rapunzel, Spielberger demeter and two Tilda Pure Original pack sizes. R3
measured the same volatility on pasta (195/195 priced in one run, 141/195 in
the next) and correctly concluded the extractor is right to return nothing.

But the *product* consequence was not drawn: **a research answer built from one
crawl silently omits a third of the category.** Nothing is wrong and the
conclusion is incomplete.

---

## Proposed roadmap changes

Ordered by what each unblocks, with the measurement that argues for it.

### R5 — Reviews: **reclassify DONE**, and restate what it was

Shipped here as `extraction/reviews.py` + `validation/reviews.py`, 74 tests.
The entry should record that the decision test passed, that the cost estimate
was wrong in an instructive direction (parsing, not crawling), and that
`/product-reviews/` requires authentication — so nobody re-scopes the expensive
version later.

### R6 — A command line for the things every category needs — **NEXT**

The cheapest item here and the one with the clearest evidence: four scripts
written and discarded in one afternoon. Nothing new is required, only exposing
what exists.

```
amazon_scraper.run reextract <run_dir> [--feed old.jsonl] -o new.jsonl
amazon_scraper.analysis <cmd> feed1.jsonl feed2.jsonl ...   # merge by ASIN
amazon_scraper.analysis shortlist <feeds> --category X --limit N
amazon_scraper.analysis cards <feeds> ASIN ASIN ASIN
```

**Done when** the basmati shortlist (kept locally under `reports/`, which is
gitignored — see `reports/README.md`) is reproducible with shipped commands and
no scratch scripts.

### R7 — Attributed search: separate *finding* a claim from *crediting* it

The 29/53 parboiled error above, plus the reseller case, are the same bug
wearing two hats: text on an Amazon page is not necessarily about the product
the page sells.

Two pieces, both generic:

1. **`search(..., scope=...)`** in the validation layer, with named scopes —
   `self` (title, ingredient declaration, attribute rows) versus `page`
   (everything, including A+ and cross-sell bullets). Today each category
   hand-rolls its own field tuple; mounting paste and basmati have now done it
   independently, which is the second occurrence that R2's own promotion rule
   asks for.
2. **Negation-aware matching**, so "mineralölfrei" and "Non-parboiled" stop
   reading as declarations of the thing they deny. Mounting paste needs this
   as badly as basmati does — its whole claim set is "free of X".

**Done when** rerunning both categories over their saved corpora changes no
true positive and removes the known false ones, pinned by test.

### R8 — Marketplace-aware text matching

`\bword\b` is not a safe default on a compounding language, and amazon.de is
the only validated marketplace. A `Marketplace.word(stem)` helper that emits
`\bstem` for German and `\bstem\b` for English puts this one decision next to
the other locale decisions instead of in every category's regexes.

Cheap, and it removes an entire class of silent 15% losses.

### R9 — A second pass for missing prices

31% of the category unpriced in a single crawl is a product problem, not an
extraction one. A cheap re-fetch of price-only for ASINs whose price was
`unknown`, some hours later, would recover most of them: the pages are already
identified, and the request count is a fraction of the original crawl.

**Decision test before building:** re-fetch the 73 unpriced basmati ASINs once
and count how many price. Below ~30% recovered, the listings are genuinely
dormant and this is not worth automating.

### R10 — Scoring as a shared, optional facility — **evidence insufficient, do not build yet**

Basmati needed a composite score, which `report.py` deliberately refuses to
offer, and its reasoning is quoted in full in the new module because it is
correct: a score "could not answer why A is better than B".

Three properties made a score defensible anyway, and all three look general:

- every component published with its evidence, never just the total;
- a missing input scores *neutral*, never zero — absence of data is not an
  adverse finding;
- the total is **shrunk toward neutral in proportion to how much is unknown**,
  so a listing whose whole case is its own adjectives cannot outrank one with
  an independent measurement. This is not theory: the first version ranked
  first a 10 kg bag with five ratings whose bullet claimed every heavy metal
  was below the limit of detection.

But **one category is one data point**, and this repository's own rule — proven
right in R2, where three of four "generalisations" turned out to be bugs — is
that a rule earns promotion after a *second* consumer. Dry pasta and mounting
paste both deliberately refuse to score. Leave this in `basmati_rice.py` until
something else wants it.

### E3 — Discovery coverage: **sharpened again, still open**

Brand-name queries were not optional. The broad sweep (8 generic German and
English queries, 2 pages each) **never surfaced AKASH at all** — it took a
query naming the brand. A researcher who did not already know the Stiftung
Warentest result would not have found the product it recommends.

That reframes E3 from "do our queries cover the category" to something
answerable and more useful: **generic queries systematically under-sample
diaspora brands**, which on Amazon.de are a large part of the real shelf.
Candidate experiment: take the brands discovered only by brand-specific
queries, and measure their share of the final shortlist. Here it was 1 of 8
finalists, plus 2 of the 5 external-evidence products.

### Unchanged

R4 (amazon.com) stays deferred — this question was `.de`-only and nothing
argued otherwise. Browser automation stays rejected: **537/537 HTTP 200, zero
challenges**, and the review data everyone assumes needs JavaScript is in the
server-rendered HTML. OCR stays dropped; nothing in this category was
image-only.

---

## One thing I would change about the docs

`README.md` describes offline re-extraction with a code sample, and
`ROADMAP.md` records the page store as R1's deliverable. Neither says the thing
that actually mattered on the day: **you can start a crawl before you have
finished writing the extractor.** That is the practical payoff of R1, it is
what made this afternoon work, and it reads as a storage detail rather than a
workflow.
