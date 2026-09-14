# Evidence

Crawl output that a roadmap decision rests on, committed so the numbers in
[`../../ROADMAP.md`](../../ROADMAP.md) can be re-derived rather than taken on
trust. Everything else under `data/` is working output and stays out of git —
a run retains roughly 390 KB gzipped per product page, which does not belong
in a history.

| File | What it is |
|---|---|
| `validation-amazon-de-2026-09-14.jsonl.gz` | 195 product records, three queries, Amazon.de, no proxy, no browser. Schema v2 — the set every coverage and data-quality figure in EXTRACTION.md and ROADMAP.md was measured on, and the input the R0 analysis was built against. |
| `discovery-amazon-de-2026-09-14.jsonl.gz` | 213 discovery occurrences from the R1 verification crawl: every sighting, before de-duplication. The evidence for the sponsored share and the repeat-sighting rate. |
| `discovery-amazon-de-2026-09-14.manifest.json` | That crawl's manifest — arguments, locale, counts, stats, finish reason. |

## Reading them

```bash
uv run python -m amazon_scraper.analysis summary \
    data/evidence/validation-amazon-de-2026-09-14.jsonl.gz
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

These records are schema v2; current output is v3, which adds `variation`.
They are kept as they were crawled. Re-crawling would produce different
products at different prices and would not reproduce the measurements.
