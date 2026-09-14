# 🛍️ Amazon Search Scraper — Scrapy (Python)

> Scrape Amazon **search result pages** and **product details** at scale using Scrapy & ScrapeOps.  
> Extract product URLs, titles, prices, ratings, and detailed product information.

---

## What It Does

- Crawls **Amazon search result pages** (`/s?k=…&page=…`) for given keywords  
- Extracts **detailed product information** from individual product pages
- Extracts comprehensive metadata:
  - **Title**, **Price**, **Rating**, **Product URL**, **ASIN**, **Review Count**
  - **Product Details**: Description, Brand, Availability, Seller, Images, Features, Specifications
- Built-in proxy rotation via ScrapeOps for reliable scraping
- Structured CSV output with automatic pagination support

---

## Key Features

- **Search Page Scraper**: Extracts data from Amazon search result listings
- **Product Detail Scraper**: Gets comprehensive product information
- Full Scrapy project structure with proper organization
- Structured CSV output with data validation
- Plug‑and‑play integrations:
  - ScrapeOps Proxy SDK for IP rotation and geolocation
  - ScrapeOps Monitoring SDK for real-time tracking
  - Multiple output formats: JSON, CSV, XML, JSON Lines
- Robust error handling with CSS selector fallbacks
- Automatic pagination through search results

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
│   └── settings.py                     
│   ├── extraction/              # PDP extraction layer
│   │   ├── text.py              # text / number primitives
│   │   ├── marketplaces.py      # per-locale labels, currency, formats
│   │   ├── blocks.py            # generic Amazon page structures
│   │   └── pdp.py               # composes one product record
│   ├── analysis/                # offline analysis of crawled records
│   │   ├── evidence.py          # values that carry their own provenance
│   │   ├── checks.py            # category-neutral validation
│   │   ├── pasta.py             # dry-pasta classification and claims
│   │   └── report.py            # evidence cards, comparison, ranking
│   └── settings_baseline.py     # proxy-free local profile
├── tests/
│   ├── test_extraction.py       # unit tests over hand-written fixtures
│   ├── test_corpus.py           # regression test over saved real pages
│   ├── test_analysis.py         # validation rules + the records behind them
│   ├── corpus/                  # 35 saved Amazon PDPs + expected output
│   └── cases/                   # 25 records each validation rule was built on
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

See **[EXTRACTION.md](EXTRACTION.md)** for the PDP structures investigated,
the record schema, validation results and known limitations, and
**[BASELINE.md](BASELINE.md)** for the original proxy-free crawl setup.

### 3. **Analysis layer** (`amazon_scraper.analysis`)

Runs **offline** over the JSONL a crawl produced. It fetches nothing, and
answers a different question from the extractor: not "what does the page say"
but "how much of that should we believe".

```text
records → generic checks → category knowledge → evidence cards
          (checks.py)      (pasta.py)          (report.py)
```

A populated field is not a fact. Amazon's *structured* nutrition card states
87.7 kcal/100 g for dry pasta on one record and 7 g of carbohydrate on
another; a sixteen-pack of Garofalo Gragnano reports €62.56/kg because the
vendor filed `Anzahl der Einheiten: 500 gramm` on a 16 × 500 g listing, and
Amazon's own price-per-kilo agrees with it because it is computed from the
same wrong row. So every value the analysis surfaces carries a status and the
source text behind it:

| Status | Meaning |
|---|---|
| `trusted` | survived every check that applies to it |
| `disputed` | sources on the page contradict each other, or a check failed — shown with the contradiction, never ranked |
| `unverified` | nothing contradicts it, nothing independent confirms it |
| `unknown` | we do not know; distinct from "the page does not say" |
| `not_claimed` | we searched every text field and the claim is not made — which is not the same as it being untrue |

The split between `checks.py` and `pasta.py` is the point. A generic rule can
prove that an energy figure and its own macronutrients contradict each other;
only category knowledge can say which side is wrong. On `B0C3WCFKHT` the
macronutrients are right and the vendor's kJ column is mistyped; on
`B086K1MFSL` it is the other way round. Both are resolved correctly, and
neither rule knows what pasta is.

```bash
# how much of a crawl is actually usable, and where it fails
uv run python -m amazon_scraper.analysis summary data/products.jsonl

# cheapest per kg among pastas that claim bronze-die extrusion
uv run python -m amazon_scraper.analysis rank data/products.jsonl \
    --require bronze_die --limit 15

# one product's evidence card, or the same thing as JSON
uv run python -m amazon_scraper.analysis card data/products.jsonl B08WJGD5Z5
uv run python -m amazon_scraper.analysis card data/products.jsonl B08WJGD5Z5 --json

# why one is a better buy than the other — and what cannot be compared
uv run python -m amazon_scraper.analysis compare data/products.jsonl \
    B08WJGD5Z5 B0DQ2N5HRW
```

Ranking is offered on **one axis at a time**, never as a composite score: a
score would have to weigh a trusted price against an unverified protein figure
and a claim nobody checked, and it could not answer "why is A better than B",
which is the whole point. Over the 195-record Amazon.de validation set, 143 of
161 dry pastas have at least one trusted comparison axis, 12 have a disputed
price per kg and are shown with the contradiction rather than ranked, and 34
records are classified out as not dry pasta — among them a toilet brush and a
cookbook, both returned by pasta searches.

See **[ROADMAP.md](ROADMAP.md)** for what this milestone was, what it
deliberately left out, and what comes next.

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
  "schema_version": 2,
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
    "nutrition": {"source": "nutrition_card", "confidence": "high",
                  "basis_text": "Pro 100g",
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
