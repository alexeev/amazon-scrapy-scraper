# Runtime migration — Python 3.9 / Scrapy 2.13 → Python 3.14 / Scrapy 2.19

Date: 2026-09-14. Scope: runtime and environment only. No crawler, extraction
or product-analysis features were added, and the record schema is unchanged
(`schema_version` is still `2`).

---

## 1. Runtime

| | Before | After |
|---|---|---|
| Python | 3.9.6 (macOS system Python, `/usr/bin/python3`) | 3.14.6 (managed by uv) |
| Scrapy | 2.13.4 | 2.19.0 |
| parsel | 1.10.0 | 1.11.0 |
| lxml | 6.1.3 | 6.1.3 |
| Twisted | 25.5.0 | 26.4.0 |
| Environment | `python3 -m venv` + `requirements.txt` | `uv sync` + `pyproject.toml` + `uv.lock` |
| ScrapeOps packages | required | optional extra |

### Why 3.14 and not 3.13

Scrapy 2.19 supports CPython 3.10–3.15. The choice was made from the actual
dependency set rather than from recency:

* Scrapy 2.18 made Zstandard support mandatory. On Python 3.14+ it uses the
  standard library's `compression.zstd`; on 3.10–3.13 it pulls in the
  third-party `backports.zstd`. Resolving the same requirement against both
  confirmed that is the *only* difference in the dependency graph — 3.13
  resolves to 44 packages, 3.14 to 43, and `backports-zstd` is the one that
  drops out. Fewer compiled third-party dependencies is a real
  reproducibility win for no cost here.
* Every compiled dependency (lxml 6.1.3, cryptography 50.0.1, Twisted 26.4.0)
  ships macOS arm64 wheels for 3.14, so `uv sync` never builds from source.
* 3.15 is still in beta and Scrapy's support for it landed only in 2.19.
  Nothing in this project needs it.

The version is pinned in `.python-version` and bounded in `pyproject.toml`
(`requires-python = ">=3.14,<3.15"`), so the interpreter is as reproducible
as the dependency set.

---

## 2. uv adoption — decision

**Adopted.** `pyproject.toml` + `uv.lock` are now the single source of truth;
`requirements.txt` has been deleted.

`requirements.txt` carried three unpinned floors (`scrapy>=2.5.0` and two
ScrapeOps packages) and no lock, so "install the dependencies" resolved to
something different on every machine and every day. Since the interpreter had
to change anyway, the environment layer was the cheaper half of the same
problem:

* **Reproducible interpreter** — uv installs CPython 3.14 itself. The macOS
  system Python, which was the previous source of the urllib3/LibreSSL
  startup warnings, is out of the picture.
* **Reproducible resolution** — `uv.lock` is committed and pins every
  package with a SHA-256 hash: 43 installed by a default `uv sync`, 49
  including the optional ScrapeOps extra.
* **One command to onboard** — `uv sync` on a clean machine, with no
  `activate` step. `uv run` re-checks the lock before every command, so a
  stale environment is not a failure mode.
* **No packaging ceremony** — `[tool.uv] package = false`. This repository is
  a Scrapy project, not a library: there is nothing to build or publish, and
  it was not turned into a distributable package to satisfy the tool.

`requirements.txt` was not kept as a compatibility shim, because two
dependency lists drift apart. Anything that needs pip syntax can generate it
on demand:

```bash
uv export --format requirements-txt --no-hashes
```

**ScrapeOps became an optional extra** (`uv sync --extra scrapeops`). The
validated profile is proxy-free and never loads it, so it has no business
being a required dependency of the crawler. It was verified to import and
build under Scrapy 2.19, but the proxy profile itself has not been exercised
since the upgrade — running it needs an API key.

---

## 3. Scrapy 2.13 → 2.19 changes considered

Reviewed all release notes for 2.14.0, 2.14.1, 2.14.2, 2.15.0, 2.15.1,
2.15.2, 2.16.0, 2.17.0, 2.18.0 and 2.19.0.

### Acted on

| Release | Change | Action |
|---|---|---|
| 2.16 | `Spider.start_requests()` **removed** and no longer called | Both spiders now define `async def start()`. Without this the crawler silently issues no requests. |
| 2.15 | Component priority dictionaries are normalised by importing every key, including keys set to `None` | `settings_baseline.py` no longer names the ScrapeOps components at all. Disabling them by name made the package a hard import requirement even though the profile does not use it. |
| 2.19 | `RANDOMIZE_DOWNLOAD_DELAY` deprecated in favour of `DOWNLOAD_DELAY_JITTER` | `DOWNLOAD_DELAY_JITTER = 0.5`, which is exactly what the old boolean meant (`Slot.jitter = 0.5 * bool(randomize_delay)` in Scrapy's own code), so the delay still varies uniformly over ±50% of `DOWNLOAD_DELAY`. |
| 2.19 | New `RemoteControl` extension, **enabled by default**, serving an HTTP endpoint that executes code inside the crawl process | `REMOTE_CONTROL_ENABLED = False` in `settings.py`, so both profiles inherit it. The validated baseline had no such surface, and nothing here uses it. |
| 2.16 | Spider-middleware `process_start_requests()` support removed | The unused project middleware template now implements `async def process_start()`, matching Scrapy 2.19's own template. |

### Considered, no action needed

| Release | Change | Why it does not apply |
|---|---|---|
| 2.14 | `SCHEDULER_PRIORITY_QUEUE` now defaults to `DownloaderAwarePriorityQueue` | This crawl is single-domain, so there is one download slot and the queue degrades to the previous per-priority ordering. Verified live: both `/s?` requests preceded every PDP, and the page-2-before-page-1 PDP ordering the baseline documented is unchanged. Search pacing does not depend on the scheduler in any case — see §4. |
| 2.18 | `brotli` and Zstandard support now mandatory | Requests now advertise `Accept-Encoding: gzip, deflate, br, zstd` instead of `gzip, deflate`, so Amazon may serve Brotli or Zstandard where it previously could not. This is a genuine on-the-wire difference, handled transparently by `HttpCompressionMiddleware`; all 15 smoke responses decoded correctly. |
| 2.18 | `Crawler.stats` and friends raise `RuntimeError` before the crawl starts | The spider only reads `self.crawler.stats` inside callbacks. |
| 2.18 | New `MetaCopyDetectionMiddleware`, enabled by default | The spider builds a fresh `meta` dict for every request and never copies `response.meta`. No warning was emitted. |
| 2.18 | AutoThrottle no longer sets the `download_delay` spider attribute | Nothing reads it. |
| 2.18 | Item exporters export fields in declaration order | Records are plain dicts, whose key order is preserved as before. |
| 2.15 | `Request`/`Response` define `__slots__` | No attributes are attached to request or response objects. |
| 2.15 | Selector type no longer forced to `html` for non-HTML responses | PDPs and search pages are served as `text/html`. |
| 2.19 | aiohttp download handler becomes the default **without a reactor** | The project runs with the Twisted reactor, so the handler is unchanged. Not adopted: the task's constraint against new transports stands, and there is no problem for it to solve. |
| 2.19 | Encoding of responses that declare none is now detected with charset-normalizer | Amazon declares UTF-8. |
| 2.19 | SQLite scheduler queues, `cache_timestamp`, `Request.to_curl()`, `LOG_COLOR`, `depth_reset`, FTPS feeds, HTTP/2 promotion | Useful, but none replaces existing code here. Left for later, to keep this migration to one behavioural axis. |

---

## 4. Search pacing — preserved, and now load-bearing by design

The deliberate serialisation of `/s?` requests, added because bursts drew
HTTP 503s, is a property of the spider, not of the scheduler: `start()` seeds
exactly one search request, and every subsequent one is yielded from
`advance_search()` only after the previous search response has been parsed.
A scheduler change cannot defeat it. The docstring now says so explicitly.

Verified on the live smoke crawl:

```text
21:16:37  s?k=spaghetti+hartweizen&page=1
21:16:39  s?k=spaghetti+hartweizen&page=2      <- 2 s later, never concurrent
21:16:43  dp/B0B4JH6R69
21:16:47  dp/B01M69QS13
...       one request in flight throughout, 4-6 s apart
21:17:43  dp/B0FYQH45FT
```

Two search requests, sequential, followed by PDPs. `CONCURRENT_REQUESTS = 1`,
`DOWNLOAD_DELAY = 2.0` and AutoThrottle behave as before. Zero HTTP 503s.

---

## 5. Regression report

### 5.1 Offline — unit tests

```bash
uv run python -m unittest discover -s tests
```

22 pre-existing tests pass unchanged on the new runtime (and passed on the
old one immediately before the migration, as the control). Two tests were
added for the defect found below, bringing the suite to **24 passing**.

### 5.2 Offline — extraction over the real-page corpus

The 34 saved amazon.de PDPs and the 1 saved amazon.com PDP from the original
extraction work were re-extracted on both runtimes and compared field by
field, with the intentionally environment-dependent `fetched_at` blanked.

| Run | Result |
|---|---|
| Python 3.9.6 / parsel 1.10 (pre-upgrade) | reference |
| Python 3.14 / parsel 1.11, before the fix below | **18 field values lost across 2 of 34 records** |
| Python 3.14 / parsel 1.11, after the fix | **byte-identical to the reference** |
| Python 3.9.6 / parsel 1.10, after the fix | byte-identical to the reference |

The amazon.com sample was identical throughout.

#### The defect

`key_value_tables()` de-duplicated attribute tables by `id(table.root)`.
lxml builds an element proxy on demand and frees it as soon as nothing refers
to it, so CPython reuses the address and a later, unrelated table inherits an
already-seen id and is silently skipped. Whether that happens depends on the
allocator, which is why the upgrade surfaced it.

On the new runtime it dropped the whole `#productDetails_detailBullets_sections1`
table from two records, losing `Amazon Bestseller-Rang`, `Durchschnittliche
Kundenbewertung` and `Im Angebot von Amazon.de seit` from both `raw_tables`
and `attributes`, and shifting the provenance of `ASIN` from `table` to
`detail_bullets`. Isolating the variables showed the Python version, not
parsel, was responsible: Python 3.14 with parsel 1.10 reproduced it exactly.

The fix keeps the element proxies in a list instead of reducing them to `id()`
values, so their identity stays meaningful for as long as the comparison
needs it. `tests/test_extraction.py::KeyValueTables` covers both halves —
that each table is read exactly once, and that the result does not depend on
object lifetimes. Both new tests fail against the old implementation.

This was a latent bug, not something the upgrade introduced. It is fixed
rather than worked around because the migration must not lose data, and
because output that depends on memory-allocation happenstance cannot be
regression-tested at all.

### 5.3 Offline — settings resolution

The fully resolved component lists (downloader middlewares, spider
middlewares, extensions, item pipelines) and the pacing settings
(`CONCURRENT_REQUESTS`, `CONCURRENT_REQUESTS_PER_DOMAIN`, `DOWNLOAD_DELAY`,
jitter, `AUTOTHROTTLE_ENABLED`, `RETRY_TIMES`) were diffed between the
original and the migrated `settings_baseline.py` on Scrapy 2.19, with the
ScrapeOps packages installed so both versions could load. **Identical.**

With the packages absent, the migrated settings resolve identically and the
original ones fail to load at all.

### 5.4 Live — Amazon.de smoke crawl

```bash
SCRAPY_PROJECT=baseline uv run scrapy crawl amazon_product \
  -a keyword="spaghetti hartweizen" \
  -a domain="www.amazon.de" \
  -a max_pages=2 \
  -s CLOSESPIDER_ITEMCOUNT=12 \
  -O data/smoke_upgrade_amazon_de.jsonl
```

2026-09-14, 21:16:35–21:17:43 local (CEST), 68.5 s elapsed.

| Metric | Value |
|---|---|
| HTTP requests | 15 |
| HTTP 200 | 15 (100%) |
| HTTP errors | 0 |
| Retries | 0 |
| Download errors | 0 |
| **CAPTCHA / Robot Check** | **0** |
| Search pages parsed | 2 (pagination exercised) |
| Product URLs discovered | 146 |
| Unique ASINs enqueued after dedupe | 116 |
| PDP records emitted | 13 |
| PDP parser failures | 0 |
| Extraction errors | 0 |
| `finish_reason` | `closespider_itemcount` |

Output validity, all 13 records: valid JSONL, 13 unique ASINs, `schema_version`
2, `search_query` / `search_page` / `search_position` lineage present, both
search pages represented, `marketplace` and `product_url` on `amazon.de`, zero
`.com` leakage.

Coverage on this small, uncontrolled live sample: title 13/13, brand 13/13,
breadcrumbs 13/13, raw tables 13/13, images 13/13, important information
13/13, ingredients 13/13, total quantity 13/13, feature bullets 12/13, rating
12/13, price 10/13, nutrition 11/13. The 3 records without a price had no buy
box: the extractor listed `price` in `extraction.blocks_absent` rather than
reading a neighbouring carousel's price, which is the behaviour the price
tests pin down, and those same records carry no availability text either.

Diagnostics confirmed operational: `amazon/challenge/*`, `amazon/http_error/*`,
`amazon/download_error`, `amazon/pdp_parse_failed`, `amazon/block_error/*` and
the `amazon/field/*` coverage counters were all wired and reported.

Record schema was compared against the 195-record pre-upgrade validation
crawl: top-level keys identical, and the only key paths present there but not
in the smoke output are the four conditional `package.package_weight_*` fields,
which none of these 13 products publish. The corpus comparison in §5.2 shows
those fields still populate identically — 12 of 34 corpus records carry them,
before and after.

---

## 6. Remaining warnings and technical debt

* **Zero deprecation warnings** from Scrapy or from project code during the
  crawl (`grep -ic deprecat` over a full DEBUG log: 0). The
  `start_requests()` warning noted in BASELINE.md §5 is resolved.
* `tldextract` logged two warnings while failing to fetch the Public Suffix
  List over the network, falling back to its bundled snapshot. This is
  environment noise from a sandboxed network, not a code or upgrade issue;
  offsite filtering behaved correctly and no request was wrongly dropped.
* **The ScrapeOps profile is unvalidated.** Its three components import and
  build under Scrapy 2.19, but no crawl has been run through it since the
  upgrade, because that needs an API key. If it is ever used again it needs
  its own smoke test.
* **`amazon_scraper/spiders/amazon_search.py`** still carries the upstream
  hardcoded `.com` URLs, the inline `['ipad']` keyword list and the
  off-by-one pagination bug documented in BASELINE.md §6. Only its
  `start_requests()` → `start()` signature was migrated, so that it still
  runs; the rest is out of scope here.
* **`middlewares.py`, `items.py` and `pipelines.py`** remain unmodified
  `scrapy startproject` scaffolding and are not enabled by either settings
  profile. `middlewares.py` was brought in line with Scrapy 2.19's template
  so that it would work if it were ever switched on.
* **The offline corpus is not in the repository.** The 34 saved PDPs used for
  §5.2 live outside version control, which makes the strongest regression
  asset the least durable one. Committing a compressed corpus, or a script
  that rebuilds it, would be worth doing before the next extraction change.

---

## 7. Observed differences

| Area | Difference |
|---|---|
| Extraction output | **None.** Byte-identical over the corpus once the `id()` defect was fixed. |
| Record schema | None. |
| Search pacing | None. |
| Request ordering | None. Search-before-PDP and page-2-before-page-1 PDP ordering both preserved under the new default priority queue. |
| HTTP success rate | 15/15, matching the baseline's 100%. |
| Challenge behaviour | None observed, as before. |
| On the wire | `Accept-Encoding` now advertises `br` and `zstd` in addition to `gzip, deflate`. |
| Crawl process | The `RemoteControl` HTTP endpoint that Scrapy 2.19 would enable by default is explicitly disabled. |
