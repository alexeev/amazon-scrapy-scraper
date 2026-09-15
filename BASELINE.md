# Amazon.de baseline crawl — setup, commands and smoke-test report

> **Historical record.** This documents the original baseline validation of
> 2026-09-14, on **Python 3.9.6 / Scrapy 2.13.4**, which is no longer the
> project runtime. The commands in §1–§4 are kept as written so the reported
> results stay reproducible in context; for how to set up and run the project
> today see [README.md](README.md). The move to Python 3.14 / Scrapy 2.19
> re-verified extraction against these numbers and changed none of them. The
> crawl behaviour described here, including the search pacing, is unchanged.

Scope: verify that this existing Scrapy project can traverse
`search → pagination → PDP → JSONL` on **amazon.de**, from a local machine,
with no proxy and no ScrapeOps account. This is a smoke test, not the final
pasta-quality parser.

---

## 1. Environment setup

macOS / zsh, from the repository root:

```bash
python3 -m venv .venv
```

```bash
.venv/bin/python -m pip install --upgrade pip
```

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Resolved versions: Python 3.9.6 (macOS system Python), **Scrapy 2.13.4**.
No dependency versions were changed; `requirements.txt` is untouched.

## 2. Spider discovery

```bash
.venv/bin/scrapy list
```

```text
amazon_product
amazon_search
```

The proxy-free profile is a named settings module, selected with
`SCRAPY_PROJECT=baseline`:

```bash
SCRAPY_PROJECT=baseline .venv/bin/scrapy list
```

## 3. Amazon.de HTTP sanity check

```bash
SCRAPY_PROJECT=baseline .venv/bin/scrapy shell "https://www.amazon.de/s?k=spaghetti+hartweizen"
```

Result (2026-09-14):

```text
HTTP status        200
title              "Amazon.de : spaghetti hartweizen"
body size          2,244,638 bytes
div.s-result-item  82  (70 with a non-empty data-asin)
pagination         ['Zurück', '1', '2', '3', '4']
CAPTCHA markers    none
```

A real search page was served to a plain Scrapy request on an ordinary
residential connection. Amazon did **not** block or challenge it.

## 4. Smoke crawl

```bash
SCRAPY_PROJECT=baseline .venv/bin/scrapy crawl amazon_product \
  -a keyword="spaghetti hartweizen" \
  -a domain="www.amazon.de" \
  -a max_pages=2 \
  -s CLOSESPIDER_ITEMCOUNT=25 \
  -O data/smoke_amazon_de.jsonl
```

`CLOSESPIDER_ITEMCOUNT` is stock Scrapy and keeps the run small; without it
`max_pages=2` would enqueue ~120 unique PDPs.

Single-page variant used to verify the pagination bound:

```bash
SCRAPY_PROJECT=baseline .venv/bin/scrapy crawl amazon_product \
  -a keyword="spaghetti hartweizen" \
  -a domain="www.amazon.de" \
  -a max_pages=1 \
  -s CLOSESPIDER_ITEMCOUNT=2 \
  -O data/maxpages1.jsonl
```

---

## 5. Smoke-test report

| | |
|---|---|
| Date/time | 2026-09-14, 18:51:47–18:54:05 local (CEST), 138 s elapsed |
| Query | `spaghetti hartweizen` |
| Marketplace | `www.amazon.de` |
| max_pages | 2 |
| Item cap | `CLOSESPIDER_ITEMCOUNT=25` |
| Output | `data/smoke_amazon_de.jsonl` |

### Counts

| Metric | Value |
|---|---|
| Search pages requested | 2 |
| Search pages successfully parsed | 2 |
| Product URLs discovered | 145 (73 on page 1, 72 on page 2) |
| Duplicate PDP URLs suppressed by Scrapy's dupefilter | 27 |
| PDP requests attempted | 26 |
| Normal PDP responses (HTTP 200, not a challenge) | 26 |
| PDP records emitted | 26 |
| **Challenge / CAPTCHA responses** | **0** |
| **HTTP errors** | **0** (`response_status_count/200: 28`, 28/28) |
| **Parser failures** (200, not a challenge, no `#productTitle`) | **0** |
| Retries | 0 |
| `finish_reason` | `closespider_itemcount` |

### Output quality (26 records)

| Field | Populated |
|---|---|
| `name` | 26/26 |
| `price` | 26/26 |
| `stars` | 26/26 |
| `rating_count` | 24/26 |
| `feature_bullets` | 19/26 |
| `images` | 0/26 — see note below |

Lineage and marketplace integrity:

```text
valid JSONL lines            26  (one JSON object per line)
unique ASINs                 26
search_query preserved       all records: "spaghetti hartweizen"
search_page preserved        page 1 and page 2 both represented
product_url on amazon.de     26/26
amazon.com leakage           none
```

`max_pages=1` run: `amazon/search_pages_parsed: 1`, no page-2 request issued.

### Notes

* **PDP ordering.** Scrapy's default scheduler is LIFO, so page-2 PDPs are
  fetched before page-1 PDPs. With the 25-item cap the split landed at
  24 records from page 2 and 2 from page 1. Both pages produced PDPs, which
  is what the test needed to show; it is not a bug.
* **`images` is empty on amazon.de.** The upstream regex requires
  `...'initial': [...]},\n` with a literal newline. `colorImages`,
  `'initial'` and `ImageBlockATF` *are* present in amazon.de's
  server-rendered HTML — only the whitespace assumption fails. Left unfixed
  (out of scope), but it confirms the image data needs no browser.
* **Startup warnings** are environment noise, not crawl problems:
  urllib3/LibreSSL on macOS system Python, and a Scrapy 2.13 deprecation of
  `start_requests()` in favour of `async def start()`. `start_requests()`
  still works and keeps compatibility with the pinned `scrapy>=2.5.0`.
  *(Both are gone as of the 2.19 migration: Scrapy 2.16 removed
  `start_requests()` outright, and the system Python is no longer used.)*

---

## 6. Change summary

| File | Change | Why |
|---|---|---|
| `amazon_scraper/settings_baseline.py` | **New.** Overlays `settings.py`; disables the ScrapeOps proxy, monitor and retry middleware, restores Scrapy's own `RetryMiddleware`, and applies the conservative local profile. | Baseline must run with no API key. Upstream ScrapeOps config stays intact in `settings.py` for later use. |
| `scrapy.cfg` | Registered `baseline = amazon_scraper.settings_baseline`. | Standard Scrapy mechanism for selecting the profile via `SCRAPY_PROJECT`. |
| `amazon_scraper/spiders/amazon_product.py` | Runtime `keyword` / `domain` / `max_pages` args; marketplace-safe URL builders; pagination fix; challenge detection; lineage fields; removed the forced CSV feed. | See below. |
| `.gitignore` | Ignore `data/` and `*.jsonl`. | Keep crawl output out of the repo. |

No API keys or secrets were added. `amazon_scraper/spiders/amazon_search.py`
was deliberately left untouched — it is outside this task's scope and still
carries the hardcoded `.com` URLs and the off-by-one pagination bug.

### Spider changes in detail

1. **Runtime arguments.** `__init__(keyword, domain, max_pages)` replaces the
   hardcoded `keyword_list = ['ipad']`. Defaults are `spaghetti hartweizen`
   / `www.amazon.de` / `2`.
2. **Marketplace-safe URLs.** `search_url()` and `product_url()` are the only
   places a URL is built, both from `self.base_url`. The hardcoded
   `urljoin('https://www.amazon.com/', ...)` is gone, so a `.de` run cannot
   construct a `.com` URL. `allowed_domains` is set from the same host.
3. **Pagination off-by-one fixed.** Upstream `range(2, int(last_page))`
   dropped the last page. Now `range(2, min(max_pages, last_page) + 1)`.
   `last_search_page()` also takes the max of the *numeric* pagination
   entries — the upstream XPath returns `['Zurück', '1', '2', '3', '4']` on
   amazon.de, and a layout where `Weiter` sorts last would crash `int()`.
4. **Challenge detection.** `challenge_reason()` checks for CAPTCHA form
   markup and Robot-Check text (English and German) before any parsing.
   Challenges are counted in `amazon/challenge/{search,pdp}` and logged at
   WARNING, so a 200-response challenge page can never be mistaken for a PDP.
5. **Failure modes are separated in stats:** `amazon/challenge/*` (blocked),
   `amazon/pdp_parse_failed` (200, not a challenge, no title),
   `amazon/http_error/<status>` and `amazon/download_error` (via `errback`).
6. **Lineage fields** added to every record: `search_query`, `search_page`,
   `marketplace`, `asin`, `product_url`.
7. **Forced CSV feed removed.** `custom_settings = {'FEEDS': {...csv}}` would
   have written a timestamped CSV *in addition to* any `-O` target, since
   `-O` merges into `FEEDS`. Output is now purely runtime-selected.
8. **Search priority.** Search requests carry `priority=10` so pagination is
   exercised before the PDP queue drains — otherwise a `CLOSESPIDER_*` limit
   could end the run before page 2 is ever fetched.

### Selector changes required for amazon.de

Only two, both forced by current markup:

| Selector | Upstream | Now | Reason |
|---|---|---|---|
| Product link | `h2 a::attr(href)` | `div.s-result-item[data-asin]` → build `/dp/{asin}` | Returns **0 matches** on amazon.de: the `<a>` is now an *ancestor* of `<h2>`, not a descendant. `data-asin` is on the container, is more robust, gives ASIN for free, avoids `/sspa/click` sponsored redirects, and cannot mix marketplaces. Also gives free dedup via Scrapy's dupefilter. |
| Review count | `div[data-hook=total-review-count]` | same, falling back to `#acrCustomerReviewText` | The `data-hook` element is not rendered on amazon.de. The `.com` selector is kept first. |

`#productTitle`, `#feature-bullets li`, `span.a-price-whole` /
`span.a-price-fraction` and `span.a-icon-alt` all work unchanged on
amazon.de.

---

## 7. Recommendation

**Option 1 — proceed with the rich PDP parser using plain Scrapy.**

Evidence: 28/28 requests returned HTTP 200, zero challenges, zero retries,
zero HTTP errors, and 26/26 retrieved PDPs parsed to a complete record. The
search, pagination and PDP stages all work over an ordinary local connection
at ~2–4 s/request with no proxy. A spot check also found `nutrition`,
`Zutaten` and the image JSON present in the server-rendered PDP HTML, so the
pasta-quality fields are very likely reachable without browser automation.

Caveats worth carrying into the next task: this is a single 138-second,
28-request sample, so it does not prove behaviour over a long run — keep the
challenge counters and watch `amazon/challenge/*` as volume grows. Some
target fields will still need per-field investigation (HTML vs embedded JSON
vs A+ content), which is Option 2 work that can be done inside Option 1
rather than before it.

There is no evidence justifying Playwright, Selenium or proxy infrastructure.
