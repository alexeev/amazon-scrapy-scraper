# Amazon product research with Scrapy

Collect Amazon product pages, preserve their evidence, validate extracted
values, and compare products using category-specific rules. The active spider
is **`amazon_product`**; it handles search, pagination, and direct ASIN fetches.

## Start here

| Need | Read |
|---|---|
| Operate or maintain the repository as an agent | [AGENTS.md](AGENTS.md) — canonical instructions for either provider stack |
| Research a product or try the offline example | [RESEARCH.md](RESEARCH.md) — current runbook and commands |
| Understand fields and trust semantics | [CONTRACT.md](CONTRACT.md) — extraction schema **6**, validation contract **1** |
| Understand priorities and previous decisions | [ROADMAP.md](ROADMAP.md) |
| Understand the agent transition | [AGENT_TRANSITION_PLAN.md](AGENT_TRANSITION_PLAN.md) — T0 delivered; later stages planned |

`CLAUDE.md` is a thin entry point to the same instructions. If an agent does
not automatically discover repository instructions, tell it to read
`AGENTS.md` and `RESEARCH.md` before starting. There is no provider SDK or API
credential required for crawling, analysis, or tests.

## Supported scope

- **Amazon.de** is the validated research marketplace, with an explicit German
  acquisition locale. Its baseline profile uses no proxy or browser.
- Amazon.com has one committed product-page regression fixture and historical
  probes; full marketplace support remains deferred (R4). Amazon.co.uk and
  Amazon.it profile entries are not validated support. The `.it` profile uses
  German labels; unknown domains fall back to English. Do not treat successful
  parsing or a profile entry as proof that a marketplace is supported.
- Three category analyzers ship: `dry_pasta`, `tyre_mounting_paste`, and
  `basmati_rice`. Their defaults reflect particular use cases; a ranking alone
  does not establish suitability for a new question.
- These commands produce analysis, not an automatically verified purchase
  report. The researcher still establishes requirements, checks external
  sources, writes the report, and records the limits of the evidence.

## Setup and first check

Run commands from the repository root. The project uses CPython **3.14** and
Scrapy **2.19.x**, with dependencies declared in `pyproject.toml` and pinned in
`uv.lock`. Install `uv` using your environment's package manager if absent.
Setup may download the interpreter and packages; the example below is offline
after setup.

Both PowerShell and POSIX shells:

```text
uv sync --locked
uv run --offline --locked python -m unittest discover -s tests
```

`--locked` checks that the committed lock matches the project; do not regenerate
it as a side effect of ordinary research. No virtualenv activation is needed.

Select the validated profile explicitly. **The default in `scrapy.cfg` is
still ScrapeOps**, not the local baseline; changing that belongs to T1.

PowerShell:

```powershell
$env:SCRAPY_PROJECT = 'baseline'
$env:PYTHONIOENCODING = 'utf-8'
uv run --offline --locked scrapy list
```

POSIX shell:

```sh
export SCRAPY_PROJECT=baseline
export PYTHONIOENCODING=utf-8
uv run --offline --locked scrapy list
```

The expected spider list is just `amazon_product`. Listing spiders makes no
marketplace requests. These variables apply to subsequent commands in the
same shell; a newly opened shell needs them again.

Start with the [offline research walkthrough](RESEARCH.md#offline-walkthrough).
It uses committed evidence, requires no account, and shows both a usable
comparison and a disputed value that must not decide a purchase.

## Architecture

| Layer | Entry points | Responsibility |
|---|---|---|
| Acquisition | `amazon_scraper/spiders/amazon_product.py` | Search and direct ASIN requests, deduplication, challenge detection, coverage stats |
| Run evidence | `amazon_scraper/run.py` | Manifest, discovery log, retained PDPs, offline re-extraction |
| Extraction | `amazon_scraper/extraction/` | Amazon structures and locale profiles; raw and normalized data, per-block diagnostics |
| Validation | `amazon_scraper/validation/` | Quantity, pricing, nutrition, review and variation checks; evidence-bearing values |
| Category analysis | `amazon_scraper/analysis/categories/` | Classification, meaningful claims and comparison axes; category plausibility profiles |
| Analysis CLI | `amazon_scraper/analysis/__main__.py`, `report.py`, `feeds.py` | Feed merging, evidence cards, rankings, comparisons and summaries |

`items.py`, `pipelines.py`, and `middlewares.py` are inherited scaffolding;
they are not the research data model. The product spider emits dictionaries.
The core contract is `PdpExtractor.extract(...) -> record`, followed by
`validate(record, profile) -> Validated`, then a category's `evaluate(record)`.

### Evidence and trust

Every validated value distinguishes **source** (how it was obtained) from
**status** (which checks it survived), with quotes and field references.
`trusted`, `disputed`, `unverified`, `unknown`, and `not_claimed` have distinct
meanings; see [the contract](CONTRACT.md#status-vocabulary).

A trusted vendor declaration establishes that the page makes the claim; it is
not independent proof of product performance. Absence of a claim is not proof
it is false. The sampled review cards cannot establish a complaint rate.
Disputed numeric values are shown with their contradictions and are not used
as ranking values.

### Category behavior

| Category | Default `rank` axis | Additional evidence |
|---|---|---|
| `dry_pasta` | Price per kilogram, lower first | Ingredients, processing claims, nutrition plausibility |
| `tyre_mounting_paste` | Pack quantity, lower first | Drying, material compatibility, adverse lubricant claims |
| `basmati_rice` | Price per kilogram, lower first | Cultivar, review signals, historical external findings, a seven-component score on text cards |

`rank` sorts one axis. **It does not rank by basmati's composite score**.
Basmati's JSON card currently omits the score and several category-specific
evidence sections; consult the text card and module when researching it.
`--require` filters on an observed trusted claim, not independent certification.
Use explicit `--category`; the CLI otherwise defaults to `dry_pasta`.

Variants are grouped using Amazon's variation matrices: pack sizes can share
an offer, while non-size dimensions are retained. Missing matrices do not
justify guessed product identity. Do not merge marketplaces or rank grams and
millilitres together; current merge/group/rank safeguards are incomplete.

### Commands

| Command | Output |
|---|---|
| `python -m amazon_scraper.analysis summary FEED --category CATEGORY` | Classification decisions, evidence availability and trust statuses; not classifier accuracy |
| `... rank FEED --category CATEGORY --limit 10` | One-axis ranking, pack variants and exclusions |
| `... card FEED ASIN [ASIN ...] --category CATEGORY` | Text evidence cards; `--json` emits one pretty-printed object per ASIN |
| `... cards FEED --category CATEGORY --json` | JSONL cards for category matches; category extras are not yet complete |
| `... compare FEED ASIN ASIN --category CATEGORY` | Differences supported by comparable values and reasons for refusal |
| `... validated FEED --category CATEGORY` | JSONL validation using that category's plausibility profile; no category claim evaluation |
| `python -m amazon_scraper.run reextract RUN_DIR --feed ORIGINAL_FEED -o NEW_FEED` | Offline extraction from retained pages |

Run these with `uv run --offline --locked`. The analysis commands accept
multiple JSONL or `.jsonl.gz` feeds. They merge by ASIN and choose the newest
`fetched_at`; timestamp ties keep the first encountered record. Mixing
marketplaces is unsafe. JSON output puts the provenance summary on stderr;
do not combine stderr with the data stream. `--json` formats cards, not a
structured ranking or summary.

The `validated` CLI always supplies a category profile (default `dry_pasta`).
For neutral validation, the Python API is `validate(record)` with no profile;
that is also what the saved-page validation snapshots test. There is no
neutral CLI switch today.

## Collecting and retaining evidence

Use the [bounded live workflow](RESEARCH.md#live-collection) after recording the
question and collection limits. Keep the baseline pacing: concurrency 1,
9-second configured delay with jitter and AutoThrottle. Do not infer that an
old successful fast crawl is a current rate recommendation.

| Spider argument | Meaning |
|---|---|
| `keyword` | Semicolon-separated queries; defaults to `spaghetti hartweizen` |
| `asin` | Named ASINs or product URLs; explicit ASINs alone suppress the default query |
| `domain` | Defaults to `www.amazon.de` |
| `max_pages` | Search pages per query, default 2 |
| `max_products_per_query` | Per-query discovery cap; default 0 means unlimited |
| `keep_pages` | Default 1; keep it enabled for replay |

The product feed is written wherever `-O` specifies; there is no automatic CSV
feed. `-O` overwrites that output, so choose a new path for each collection.
Nested product records should be stored as JSONL. Each crawl separately writes:

```text
data/runs/<run_id>/manifest.json
data/runs/<run_id>/discovery.jsonl
data/runs/<run_id>/pages/<ASIN>.html.gz
```

The manifest records arguments, locale, counts, stats and finish reason.
Discovery logs preserve sightings before deduplication. Retained pages support
later extraction without another request. Run/page hashes, guaranteed unique
run IDs, complete failure capture, and portable study manifests are still T1+
work; see the [runbook limitations](RESEARCH.md#current-limitations).

## Maintenance and reference material

Use [AGENTS.md](AGENTS.md#maintenance-workflow) for the change and verification
sequence. The regression suite includes 39 saved PDPs (38 `.de`, one `.com`),
a search page, and category cases. Read [corpus instructions](tests/corpus/README.md)
before promoting a capture or regenerating snapshots. A snapshot update is
a reviewed behavior change, not a routine way to fix a failing test.

Adding a category normally means a module under `analysis/categories/`, registered
through that package's `__init__.py`, plus tests. Start at `Category`, `Axis`,
`Claim`, and `CategoryProfile`; keep generic trust rules in validation. Use
`Marketplace.word(stem)` for supported locale-aware word boundaries and the
contract's attributed search controls where appropriate. See R7/R8 in the roadmap.

Historical evidence and its limits:

- [BASELINE.md](BASELINE.md): original 2026-09-14 setup and smoke measurement.
- [EXTRACTION.md](EXTRACTION.md): extraction investigation and dated coverage.
- [USABILITY.md](USABILITY.md): basmati research postmortem and later resolutions.
- [data/evidence](data/evidence/README.md): committed crawl evidence for decisions.
- [reports](reports/README.md): output conventions; complete original study
  inputs and finished reports are not all committed.

### Legacy search-spider migration

T0 removed `amazon_search` after a tracked-reference inventory found no code or
test consumer outside the spider itself. It hardcoded an iPad query on `.com`
and emitted a different CSV record shape. Use `amazon_product` with explicit
`keyword`/`asin`, locale and bounds. Its `discovery.jsonl` records search
sightings; its JSONL feed contains product details. This is not a drop-in
replacement for the old CSV shape or a search-only crawl. Historical documents
retain the old name as part of their original measurements.

### Troubleshooting

| Symptom | Action |
|---|---|
| `ModuleNotFoundError: scrapeops_scrapy` | Select `SCRAPY_PROJECT=baseline` in the current shell and check `scrapy list`. |
| Locale conflict on startup | Confirm baseline/German headers and `.de`; do not bypass the check. |
| No or few records | Inspect manifest challenge/HTTP/parse counters, query coverage, and caps. HTTP 200 or `finished` is not proof of usable coverage. |
| uv cache is not writable | Set `UV_CACHE_DIR` to a writable directory; `data/.uv-cache` is an ignored local option. Retry locked setup. |
| Offline dependency error | Complete `uv sync --locked` first; offline mode cannot download missing packages or Python. |
| Unicode output error | Set `PYTHONIOENCODING=utf-8` as above; use UTF-8 when saving reports. |

For the cache override, use `$env:UV_CACHE_DIR = 'data/.uv-cache'` in PowerShell
or `export UV_CACHE_DIR=data/.uv-cache` in a POSIX shell. Do not delete a shared
cache or change dependency versions to work around a filesystem error.

The optional ScrapeOps profile requires `uv sync --locked --extra scrapeops`,
private credential configuration, and a matching locale. It is not part of
the validated baseline. `settings.py` currently has a placeholder key and does
not load one from the environment; do not commit a real key there. Prefer the
baseline for supported research. The default-profile/credential cleanup is T1.

## License and origin

See [LICENSE](LICENSE). Based on the Amazon scraper from
`python-scrapy-playbook/amazon-python-scrapy-scraper`, with optional ScrapeOps
integrations retained. Dependency source of truth is `pyproject.toml` plus
`uv.lock`; no separate requirements file is maintained.
