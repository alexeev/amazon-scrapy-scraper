# 🛍️ Amazon Search Scraper — Scrapy (Python)

> Scrape Amazon **search result pages** and **product details** at scale using Scrapy & ScrapeOps.  
> Extract product URLs, titles, prices, ratings, and detailed product information.

---

## What It Does

A product-research platform for Amazon, built in three layers that can be
worked on separately:

- **Acquisition** — crawls search result pages (`/s?k=…&page=…`), then the
  product pages behind them, recording every sighting and retaining every page
  so a later question costs no second crawl.
- **Extraction** — turns one page into a rich record and says where each value
  came from. Knows nothing about any product category.
- **Validation** — decides how much of that record holds up, against a
  published, versioned [contract](CONTRACT.md). Knows nothing about any
  product category either.
- **Category analysis** — the only layer that knows what the product *is*:
  what counts as one, which of the vendor's claims matter, and what "better"
  means. Two shipped: **dry pasta** and **tyre mounting paste**.

Dry pasta is the first real use case, not the boundary of the design. Adding
a category is one module; adding a marketplace is a profile entry.

---

## Key Features

- **Every value carries its evidence** — the verbatim source sentence and the
  field it came from, so a recommendation can be checked rather than trusted.
- **Every value carries a status** — `trusted`, `disputed`, `unverified` or
  `unknown`. A number Amazon contradicts is shown with the contradiction and
  never ranked.
- **Reproducible crawls** — run manifest, locale, a discovery log written
  before de-duplication, and the retained page behind every record.
- **Offline re-extraction** — a new field costs no new crawl.
- **Category-general** — the acquisition, extraction and validation layers
  never learn what good pasta is. Two categories prove it rather than assert
  it.
- **Regression-tested against reality** — 39 saved real product pages, pinned
  field by field for both extraction and validation output.
- Works on amazon.de without a proxy or a browser; ScrapeOps proxy and
  monitoring remain available as an optional profile.

---

## Repo Structure

```bash
amazon-scrapy-scraper/
├── amazon_scraper/
│   ├── spiders/
│   │   ├── amazon_search.py      
│   │   └── amazon_product.py
│   ├── middlewares.py           
│   ├── items.py                 
│   ├── pipelines.py                       
│   ├── run.py                   # run identity, provenance, page store
│   └── settings.py                     
│   ├── extraction/              # PDP extraction layer
│   │   ├── text.py              # text / number primitives
│   │   ├── marketplaces.py      # per-locale labels, currency, formats
│   │   ├── blocks.py            # generic Amazon page structures
│   │   └── pdp.py               # composes one product record
│   ├── validation/              # the generic layer: the published contract
│   │   ├── evidence.py          # values carrying source, status and quotes
│   │   ├── quantity.py          # pack size, reconciled against the page
│   │   ├── pricing.py           # price, and price per kg / per litre
│   │   ├── nutrition.py         # nutrition checks, where a food block exists
│   │   ├── variation.py         # product families and pack sizes
│   │   └── contract.py          # validate() -> Validated; CONTRACT_VERSION
│   ├── analysis/                # category knowledge, downstream of the above
│   │   ├── category.py          # what a category declares: axes, claims
│   │   ├── categories/
│   │   │   ├── dry_pasta.py     # groceries, cheapest trustworthy kilogram
│   │   │   └── mounting_paste.py# non-food, smallest pack wins
│   │   └── report.py            # evidence cards, comparison, ranking
│   └── settings_baseline.py     # proxy-free local profile
├── tests/
│   ├── test_extraction.py       # unit tests over hand-written fixtures
│   ├── test_corpus.py           # extraction + validation over saved pages
│   ├── test_validation.py       # the generic layer and its contract
│   ├── test_analysis.py         # dry pasta + the records behind its rules
│   ├── test_mounting_paste.py   # the second category, and contract discipline
│   ├── test_run.py              # provenance, locale, discovery, page store
│   ├── corpus/                  # 39 saved PDPs + 1 search page + snapshots
│   └── cases/                   # the records each rule was built on
├── data/evidence/               # committed crawl evidence behind the roadmap
├── CONTRACT.md                  # the published schema + compatibility policy
├── ROADMAP.md                   # plan of record, with progress
├── scrapy.cfg
├── pyproject.toml               # dependencies (single source of truth)
├── uv.lock                      # exact, resolved, committed
├── .python-version              # CPython version for uv
├── .gitignore
├── LICENSE
└── README.md
```

---

## Runtime

| | |
|---|---|
| Python | CPython 3.14 (pinned in `.python-version`) |
| Scrapy | 2.19.x |
| Environment manager | [uv](https://docs.astral.sh/uv/) |
| Dependency source of truth | `pyproject.toml` + `uv.lock` |

The system Python is never used. `uv` downloads and manages the interpreter
itself, so a clean machine needs nothing but `uv`.

See **[MIGRATION.md](MIGRATION.md)** for how the project moved here from
Python 3.9 / Scrapy 2.13, and what was verified in the process.

---

## Quickstart

```bash
git clone https://github.com/Simple-Python-Scrapy-Scrapers/amazon-scrapy-scraper.git
cd amazon-scrapy-scraper
```

Install uv once, if it is not already present:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Create the environment. This installs CPython 3.14 if needed and resolves
every dependency to the exact versions in `uv.lock`:

```bash
uv sync
```

Run the tests:

```bash
uv run python -m unittest discover -s tests
```

Run the crawler. `SCRAPY_PROJECT=baseline` selects the proxy-free local
profile — the validated one, and the one to use unless you have a ScrapeOps
key:

```bash
SCRAPY_PROJECT=baseline uv run scrapy crawl amazon_product -a keyword="spaghetti hartweizen" -a domain="www.amazon.de" -a max_pages=2 -O data/products.jsonl
```

There is no `activate` step and no `pip install`: `uv run` resolves the
environment before every command, so it cannot silently drift from the lock.

### Optional: ScrapeOps proxy profile

The default settings module (`amazon_scraper.settings`, i.e. no
`SCRAPY_PROJECT`) routes traffic through ScrapeOps and needs both an API key
and two extra packages:

```bash
uv sync --extra scrapeops
```

Then set `SCRAPEOPS_API_KEY` in `amazon_scraper/settings.py`. This profile is
not part of the validated baseline and has not been exercised since the
upgrade.

---

## How It Works

### 1. **Search Spider** (`amazon_search`)
- Uses predefined keyword list (currently set to `['ipad']`)
- Generates Amazon search URLs for each keyword
- Extracts basic product information from search listings:
  - Title, price, rating, ASIN, URL, thumbnail
  - Ad detection, keyword tracking
- Uses ScrapeOps Proxy SDK for automatic IP rotation
- Automatically paginates through search results

### 2. **Product Detail Spider** (`amazon_product`)
- Crawls search results, paginates, then scrapes individual product pages
- Delegates PDP parsing to `amazon_scraper/extraction/`, which extracts:
  - identity and lineage (ASIN, marketplace, search query/page/position)
  - core data (title, brand, price, unit price, rating, availability, breadcrumbs)
  - package data (item weight, pack count, normalized total quantity)
  - content (feature bullets, description, important information, A+ content)
  - food data (ingredients, allergens, nutrition normalized per 100 g)
  - every key/value table preserved verbatim in `raw_tables`
  - the full product image gallery
- Records provenance per field, and distinguishes *absent* from *failed*
- Works without a proxy or browser on amazon.de

Run it against one or several queries (`;`-separated):

```bash
SCRAPY_PROJECT=baseline scrapy crawl amazon_product \
  -a keyword="spaghetti hartweizen; penne rigate bio" \
  -a domain="www.amazon.de" \
  -a max_pages=2 \
  -a max_products_per_query=65 \
  -O data/products.jsonl
```

| Argument | Default | Meaning |
|---|---|---|
| `keyword` | `spaghetti hartweizen` | one or more `;`-separated search queries |
| `domain` | `www.amazon.de` | marketplace host |
| `max_pages` | `2` | search result pages per query |
| `max_products_per_query` | `0` (no cap) | caps PDP discovery per query |

See **[CONTRACT.md](CONTRACT.md)** for the published record schema, the
validated record built on it and the compatibility policy;
**[EXTRACTION.md](EXTRACTION.md)** for the PDP structures investigated,
coverage results and known limitations; and **[BASELINE.md](BASELINE.md)**
for the original proxy-free crawl setup.

### 3. **Validation layer** (`amazon_scraper.validation`)

Runs **offline** over the JSONL a crawl produced. It fetches nothing, and
answers a different question from the extractor: not "what does the page say"
but "how much of that should we believe".

```text
extraction → validation → category knowledge → evidence cards
 schema v4   contract v1   categories/          report.py
```

A populated field is not a fact. Amazon's *structured* nutrition card states
87.7 kcal/100 g for dry pasta on one record and 7 g of carbohydrate on
another; a sixteen-pack of Garofalo Gragnano reports €62.56/kg because the
vendor filed `Anzahl der Einheiten: 500 gramm` on a 16 × 500 g listing, and
Amazon's own price-per-kilo agrees with it because it is computed from the
same wrong row. So every value carries two independent things and the source
text behind them:

| `status` — did it survive? | |
|---|---|
| `trusted` | survived every check that applies to it |
| `disputed` | sources on the page contradict each other, or a check failed — shown with the contradiction, never ranked |
| `unverified` | nothing contradicts it, nothing independent confirms it |
| `unknown` | we do not know; distinct from "the page does not say" |
| `not_claimed` | we searched every text field and the claim is not made — which is not the same as it being untrue |

| `source` — how was it obtained? | |
|---|---|
| `structured` | a structure Amazon renders as data |
| `attributes` | a vendor-filed key/value row |
| `text` | prose: title, bullets, description, A+ |
| `published` | a figure Amazon computed, e.g. its own unit price |
| `derived` | computed here, from other values on the record |

**A source never implies a status**, and that is a correction rather than a
nicety. The extractor used to publish a single `confidence` that mixed them,
ranking the structured card above prose — and measured over 195 records,
`high`-confidence values failed plausibility *more* often than `medium` ones
(5/45 against 2/40). Schema v4 removes it.

The full contract — both schemas, both vocabularies, what each rule checks,
and the compatibility policy — is **[CONTRACT.md](CONTRACT.md)**.

### 4. **Category analysis** (`amazon_scraper.analysis`)

A category is the only place that knows what the product is. It supplies
plausibility data, the claims worth hunting for, and what "better" means —
and it inherits trust rather than re-deriving it. Two are shipped:

| | `dry_pasta` | `tyre_mounting_paste` |
|---|---|---|
| Classified from | breadcrumbs | the **title** — Amazon files this category under four unrelated departments |
| Ranked on | price per kilogram, cheapest first | **pack size, smallest first** |
| Price per kg | the axis the category rests on | shown and explicitly refused as a ranking |
| Nutrition bands | nine | none — it is not food |
| Price band | €0.80–40.00/kg | none is defensible |

The second one is not a demo. It is the test R2 was waiting for: a non-food,
sold in tubs, tubes and aerosols, where a five-kilogram workshop tub is the
*worst* buy for somebody fitting one scooter tyre. Every trust rule
transferred unchanged; what it exposed is written up in
[CONTRACT.md §8](CONTRACT.md).

```bash
# how much of a crawl is actually usable, and where it fails
uv run python -m amazon_scraper.analysis summary data/products.jsonl

# cheapest per kg among pastas that claim bronze-die extrusion
uv run python -m amazon_scraper.analysis rank data/products.jsonl \
    --require bronze_die --limit 15

# a different category over a different crawl
uv run python -m amazon_scraper.analysis rank data/paste.jsonl \
    --category tyre_mounting_paste

# one product's evidence card, or the same thing as JSON
uv run python -m amazon_scraper.analysis card data/products.jsonl B08WJGD5Z5
uv run python -m amazon_scraper.analysis card data/products.jsonl B08WJGD5Z5 --json

# why one is a better buy than the other — and what cannot be compared
uv run python -m amazon_scraper.analysis compare data/products.jsonl \
    B08WJGD5Z5 B0DQ2N5HRW

# the contract itself, with no category interpretation on top
uv run python -m amazon_scraper.analysis validated data/products.jsonl
```

Ranking is offered on **one axis at a time**, never as a composite score: a
score would have to weigh a trusted price against an unverified protein figure
and a claim nobody checked, and it could not answer "why is A better than B",
which is the whole point.

### Adding a category

One module under `analysis/categories/`. No change to the crawler, the
extractor or the validation layer — that claim is asserted mechanically by
`tests/test_mounting_paste.py`, which parses the category's imports and fails
if it reaches past the contract into the rules.

```python
PROFILE = CategoryProfile(key='wall_paint', label='wall paint',
                          price_band=(4.0, 60.0))     # per litre

def evaluate(record):
    validated = validate(record, PROFILE)             # trust, already decided
    ...                                               # classify, hunt claims
```

### Offers, not listings

When search returns two listings of one product in different boxes, ranking
them as rivals is wrong twice: it doubles a producer's apparent presence and
implies a quality difference where only the pack differs. So rows are
**offers** — the best pack wins the row and the other sizes are named under
it.

This is uncommon: on a three-query Amazon.de crawl, 165 pasta listings were
159 offers. It is worth handling because the folded rows are interesting ones —
an Alnatura five-pack costs *more* per kilo than the single box beside it.

Grouping uses Amazon's own variation matrix, which names its own dimensions —
so the pack-size dimension is looked up, never inferred, and a product that
varies only by colour yields no pack size at all. Grouping happens **along the
size dimension only**. One real corpus family holds spaghetti, penne *and*
fusilli under a single parent ASIN; collapsing all of it would hide a
difference a cook cares about while fixing one they do not.

The bigger payoff is quantity. The same matrix is an independent statement of
what is in the box, from a different page structure than the attribute rows
that get pack sizes wrong, and on 26 records it is the only pack size the page
states at all. Used as a third reconciliation source it settled 22 quantities
and exposed 2 new conflicts — one of them a Barilla listing priced at
**€38.56/kg** because Amazon's attribute table says 1 kg and its unit price is
quoted per piece. The matrix says `10kg`; the real price is €3.86/kg.

Comparing two pack sizes of one product now says so, instead of reporting that
everything except the price is identical:

```text
  Amazon lists these as the same product in different pack sizes, not as two
  products.

    A  500 g (1er Pack)       5 EUR/kg [trusted]
    B  500 g (5er Pack)       3.6 EUR/kg [trusted]

  Only the pack size differs, so the question is which pack to buy, not which
  product is better: B wins on price per kg.
```

Over the 195-record Amazon.de pasta set, 117 of 165 dry pastas have at least
one trusted comparison axis, 131 have a pack size confirmed by an independent
statement on the page, and 30 records are classified out as not dry pasta —
among them a toilet brush and a cookbook, both returned by pasta searches.

See **[ROADMAP.md](ROADMAP.md)** for what this milestone was, what it
deliberately left out, and what comes next.

---

## Crawl provenance

Every crawl owns a directory of evidence about itself, next to the feed:

```text
data/runs/<run_id>/
  manifest.json          arguments, locale, counts, stats, finish reason
  discovery.jsonl        one line per sighting, before de-duplication
  pages/<ASIN>.html.gz   the page each record was extracted from
```

`run_id` and `locale` also travel on every product record, so a record can
always be traced back to the crawl and the language that produced it.

**Discovery is recorded before de-duplication.** One ASIN is seen many times —
under several queries, on several pages, and twice on one page, once organic
and once sponsored. Fetching its detail page repeatedly is waste, so that
stays de-duplicated; but the sightings are the answer to "what does a shopper
actually see", and they used to be dropped before anything was written down.
On the verification crawl, 213 sightings covered 170 ASINs — **20% of
sightings are repeats**, and **32% of placements are sponsored**.

**Pages are retained**, about 390 KB gzipped each, so a later extractor never
has to ask Amazon twice. Turn it off with `-a keep_pages=0`. Re-extracting a
whole run offline needs no network:

```python
from parsel import Selector
from amazon_scraper import run
from amazon_scraper.extraction import PdpExtractor, for_domain

extractor = PdpExtractor(for_domain('www.amazon.de'))
for asin, path in run.stored_pages('data/runs/<run_id>').items():
    html = run.read_page(path)
    record = extractor.extract(Selector(html), html, {'asin': asin})
```

**Locale is checked before the first request.** It used to be implicit — an
HTTP header in one module, the label vocabulary chosen from the domain in
another — and the two could disagree with no error at all, producing records
with an empty `attributes` block beside a full `raw_tables`. They *did*
disagree: Scrapy ships `Accept-Language: en`, which the non-baseline settings
profile never overrode, so crawling amazon.de on that profile asked Amazon for
English. A crawl whose locale contradicts its marketplace now refuses to
start.

---

## Example Output

### Search Results (CSV)
```csv
keyword,asin,url,ad,title,price,rating,rating_count,thumbnail_url
ipad,B09G9FPHY6,https://www.amazon.com/dp/B09G9FPHY6,False,iPad (10th generation),$449.00,4.7 out of 5 stars,12,345,https://m.media-amazon.com/images/I/71...
```

### Product Details (JSONL, abridged)
```json
{
  "schema_version": 4,
  "marketplace": "www.amazon.de",
  "asin": "B0CPQ5HGC8",
  "search_query": "penne rigate bio vollkorn",
  "search_page": 1,
  "search_position": 12,
  "title": "Naturata Bio Dinkel-Vollkorn Lasagne-Platten, 250 g",
  "brand": "Naturata",
  "price": {"amount": 3.39, "currency": "EUR", "text": "3,39 €"},
  "unit_price": {"amount": 13.56, "unit": "kg", "text": "13,56 € pro kg"},
  "rating": {"value": 4.6, "count": 209},
  "package": {"item_weight_base": 250.0, "item_count": 1,
              "total_quantity_base": 250.0, "total_quantity_unit": "g",
              "total_quantity_source": "unit_count"},
  "food": {
    "ingredients": {"text": "DINKEL-VOLLKORNMEHL** (eine WEIZENART) …",
                    "source": "nutrition_card"},
    "nutrition": {"source": "nutrition_card", "basis_text": "Pro 100g",
                  "per_100g": {"energy_kcal": 345.0, "protein_g": 12.9,
                               "carbohydrates_g": 63.5, "fat_g": 2.5}}
  },
  "raw_tables": {"Marke": "Naturata", "Artikelgewicht": "250 Gramm",
                 "Herkunftsland": "Italien"},
  "media": {"image_count": 7, "image_source": "color_images"},
  "extraction": {"blocks_absent": [], "errors": []}
}
```

---

## Config & Scaling

### Customizing Keywords
Edit the spider files to change search terms:

For `amazon_product`, pass `-a keyword="one; two; three"` — no code change
needed. `amazon_search` still carries its keyword list inline:

```python
# In amazon_scraper/spiders/amazon_search.py
async def start(self):
    keyword_list = ['your', 'keywords', 'here']
    for keyword in keyword_list:
        amazon_search_url = f'https://www.amazon.com/s?k={keyword}&page=1'
        yield scrapy.Request(url=amazon_search_url, callback=self.parse_search_results, meta={'keyword': keyword, 'page': 1})
```

(`start()` replaced `start_requests()`, which Scrapy removed in 2.16.)

### Output Configuration
The spiders automatically save to CSV files in the `amazon_scraper/data/` directory:

```python
custom_settings = {
    'FEEDS': { 'data/%(name)s_%(time)s.csv': { 'format': 'csv',}}
}
```

### Geolocation
Change the country in `amazon_scraper/settings.py`:

```python
SCRAPEOPS_PROXY_SETTINGS = {'country': 'us'}  # us, uk, ca, de, etc.
```

### Concurrency & Rate Limiting
Adjust in `amazon_scraper/settings.py`:

```python
CONCURRENT_REQUESTS = 1  # Free ScrapeOps plan limit
# CONCURRENT_REQUESTS = 10  # Paid plan
```

---

## Legal

⚠️ Scraping Amazon may violate their TOS.  
This repo is for educational purposes only. Use responsibly.

---

## Contributing

Want to add:
- More fields (variants, seller ratings)?
- Price history tracking?
- Anti-bot layer (Playwright, CAPTCHA solver)?
- Output to RAG pipelines?

→ PRs welcome!

---

## 🔗 Related Templates

In Pipeline

---

## Built With

- Scrapy 2.19 on CPython 3.14, managed with uv
- ScrapeOps Proxy SDK + Monitoring SDK (optional)
- Based on `python-scrapy-playbook/amazon-python-scrapy-scraper`

---

## 📚 Dependencies

Declared in `pyproject.toml`, locked in `uv.lock`:

- **scrapy** (`>=2.19.0,<2.20`): web scraping framework — the only required
  dependency; `parsel`, `lxml` and `twisted` come with it

Optional, in the `scrapeops` extra, for the non-baseline settings profile:

- **scrapeops-scrapy-proxy-sdk**: proxy rotation and geolocation
- **scrapeops-scrapy**: monitoring and analytics

To hand the dependency set to a tool that only speaks pip, export it rather
than maintaining a second list:

```bash
uv export --format requirements-txt --no-hashes
```

## 🆘 Troubleshooting

### No Products Found
1. Run with debug logging: `SCRAPY_PROJECT=baseline uv run scrapy crawl amazon_product -L DEBUG`
2. Check the `amazon/challenge/*` stats at the end of the run — a non-zero
   count means Amazon served a Robot Check rather than a page
3. On the ScrapeOps profile, check that the API key in
   `amazon_scraper/settings.py` is valid
4. Try different search terms

### `ValueError: Accept-Language ... asks www.amazon.de for 'en'`

The crawl refused to start because the locale it would request contradicts the
marketplace's label vocabulary, which would silently under-extract rather than
fail. Use `SCRAPY_PROJECT=baseline`, which sets a German `Accept-Language`, or
add one to `DEFAULT_REQUEST_HEADERS` in your settings profile. Scrapy's own
default is `Accept-Language: en`, so this fires on the ScrapeOps profile.

### Environment Issues
```bash
# Rebuild the environment from the lock, discarding anything stray
uv sync --reinstall
```

`uv run` recreates `.venv` whenever it does not match `uv.lock`, so an
out-of-date environment is not a failure mode you should have to think about.

### `ModuleNotFoundError: scrapeops_scrapy`
You ran without `SCRAPY_PROJECT=baseline`, so Scrapy loaded the ScrapeOps
profile. Either prefix the command with `SCRAPY_PROJECT=baseline`, or install
the extra with `uv sync --extra scrapeops`.

---

## 🔧 Enhanced ScrapeOps Integrations

### 📊 Free Monitoring Solution
Add real-time monitoring and scheduling to your scraper:
- [ScrapeOps Monitoring SDK](https://scrapeops.io/docs/monitoring/python-scrapy/sdk-integration/)
- [Monitoring Dashboard](https://scrapeops.io/monitoring-scheduling/)

### 🌐 Improved Proxy Integration
Use Scrapy Proxy SDK for better reliability:
- [ScrapeOps Proxy SDK](https://scrapeops.io/docs/web-scraping-proxy-api-aggregator/integration-examples/python-scrapy-example/)
- Solves issues with URL format changing in certain use cases

### 🔍 Amazon Website Analysis
Learn more about scraping Amazon effectively:
- [Amazon Website Analyzer](https://scrapeops.io/websites/amazon)

---

## 📖 Development Guides

The following articles go through in detail how these Amazon spiders were developed:

- [Python Scrapy: Build A Amazon.com Product Scraper](https://scrapeops.io/python-scrapy-playbook/python-scrapy-amazon-product-scraper/)
- [Python Scrapy: Build A Amazon.com Product Reviews Scraper](https://scrapeops.io/python-scrapy-playbook/python-scrapy-amazon-reviews-scraper/)

---

## 🎯 Migration Benefits

This project evolved from a simple single-file spider to a professional Scrapy structure:

- **90% Code Reduction**: From 600+ lines to ~150 lines total
- **Clean Architecture**: Each spider has a single, focused purpose
- **Easy Maintenance**: Simple, readable code structure
- **Professional Quality**: Industry-standard Scrapy project layout
- **Automatic Data Export**: CSV files with timestamps

---

## 🚀 Next Steps

1. **Get ScrapeOps API Key**: [Sign up here](https://scrapeops.io/app/register/main)
2. **Test Spiders**: Run each spider individually
3. **Customize Data**: Modify extraction logic as needed
4. **Scale Up**: Upgrade ScrapeOps plan for higher concurrency
5. **Add Features**: Implement additional spiders or data processing

The implementation provides a solid foundation for professional Amazon scraping with clean, maintainable code and robust infrastructure.
