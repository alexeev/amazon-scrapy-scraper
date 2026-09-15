# Evidence

Crawl output that a roadmap decision rests on, committed so the numbers in
[`../../ROADMAP.md`](../../ROADMAP.md) can be re-derived rather than taken on
trust. Everything else under `data/` is working output and stays out of git —
a run retains roughly 390 KB gzipped per product page, which does not belong
in a history.

| File | What it is |
|---|---|
| `validation-amazon-de-2026-09-14.jsonl.gz` | 195 product records, three queries, Amazon.de, no proxy, no browser. Schema v2 — the set every coverage and data-quality figure in EXTRACTION.md and R0 was measured on. |
| `validation-amazon-de-2026-09-15-v3.jsonl.gz` | The same three queries re-crawled under schema v3, so the records carry `run_id`, `locale` and the variation matrix. The basis for every R3 figure. |
| `validation-amazon-de-2026-09-15-v3.manifest.json` | That crawl's manifest. |
| `discovery-amazon-de-2026-09-14.jsonl.gz` | 213 discovery occurrences from the R1 verification crawl: every sighting, before de-duplication. The evidence for the sponsored share and the repeat-sighting rate. |
| `discovery-amazon-de-2026-09-14.manifest.json` | That crawl's manifest — arguments, locale, counts, stats, finish reason. |
| `validation-amazon-de-mounting-paste-2026-09-15-v4.jsonl.gz` | 90 product records, three Amazon.de queries for tyre mounting paste. The second category, and the basis for every R2 figure. |
| `validation-amazon-de-mounting-paste-2026-09-15-v4.manifest.json` | That crawl's manifest. |

## Reading them

```bash
uv run python -m amazon_scraper.analysis summary \
    data/evidence/validation-amazon-de-2026-09-14.jsonl.gz

uv run python -m amazon_scraper.analysis rank \
    data/evidence/validation-amazon-de-mounting-paste-2026-09-15-v4.jsonl.gz \
    --category tyre_mounting_paste
```

```python
from amazon_scraper import run
occurrences = run.load_discovery('data/runs/<run_id>')   # a live run
```

## Why the discovery log is separate from the records

One ASIN can be seen many times: under several queries, on several pages, and
twice on a single page — once organic and once sponsored. Fetching its detail
page repeatedly is waste, so the crawler de-duplicates. But the sightings
themselves are the answer to "what does a shopper actually see", and they used
to be discarded before anything was written down.

Measured on the crawl above: **213 occurrences of 170 distinct ASINs — 20% of
sightings are repeats**, 12 ASINs turned up under more than one query, and
**69 of 213 placements (32%) are sponsored**.

## Schema

The 2026-09-14 set is schema v2 and has no `variation` key; the 2026-09-15
pasta set is v3; the mounting-paste set is v4.

The pasta sets are kept **as crawled**, because re-crawling does not reproduce
a measurement — the two are eighteen hours apart and already disagree in a way
worth knowing about:

| | v2, 2026-09-14 | v3, 2026-09-15 |
|---|---:|---:|
| Records with a price | 195/195 | 141/195 |
| Records with `availability` | 190/195 | 137/195 |

Not an extraction change — the code produces identical output on the older set
today. Those 54 products had no purchasable offer at the later crawl time, and
the discovery log agrees: search did not price them either. Product
availability moves, and a coverage figure is a measurement of one moment.

The mounting-paste set is a different case and worth stating plainly. It was
crawled under v3 and the schema moved to v4 inside the same milestone, so it
was **re-extracted offline from that run's retained pages** — the same bytes,
read by newer code, no second request to Amazon. That is not a re-crawl and it
does not disturb a measurement; it is the capability R1 was built for, used
for the first time. Nothing else was touched: the lineage, the crawl time and
the page store are the originals.

Older records stay readable. The validation layer reads v2 and v3 records
unchanged; they simply carry fields it ignores, such as the removed
`nutrition.confidence`. Every R2 figure quoted for dry pasta was measured on
the v3 set with v4 code.
