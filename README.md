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
├── scrapy.cfg                    
├── requirements.txt              
├── .gitignore                    
├── LICENSE                      
└── README.md                   
```

---

## Quickstart

```bash
git clone https://github.com/Simple-Python-Scrapy-Scrapers/amazon-scrapy-scraper.git
cd amazon-scrapy-scraper

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure API key in amazon_scraper/settings.py:
# SCRAPEOPS_API_KEY = 'YOUR_SCRAPEOPS_API_KEY'

# Run the spiders:
cd amazon_scraper

# 1. Search for products
scrapy crawl amazon_search

# 2. Get detailed product information
scrapy crawl amazon_product
```

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

```python
# In amazon_scraper/spiders/amazon_search.py or amazon_product.py
def start_requests(self):
    keyword_list = ['your', 'keywords', 'here']
    for keyword in keyword_list:
        amazon_search_url = f'https://www.amazon.com/s?k={keyword}&page=1'
        yield scrapy.Request(url=amazon_search_url, callback=self.parse_search_results, meta={'keyword': keyword, 'page': 1})
```

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

- Scrapy (Python)
- ScrapeOps Proxy SDK + Monitoring SDK
- Based on `python-scrapy-playbook/amazon-python-scrapy-scraper`

---

## 📚 Dependencies

- **scrapy**: Web scraping framework
- **scrapeops-scrapy-proxy-sdk**: Proxy rotation and geolocation
- **scrapeops-scrapy**: Monitoring and analytics

## 🆘 Troubleshooting

### No Products Found
1. Check your ScrapeOps API key is valid in `amazon_scraper/settings.py`
2. Run with debug logging: `scrapy crawl amazon_search -L DEBUG`
3. Try different search terms

### Virtual Environment Issues
```bash
# Ensure virtual environment is activated
.venv\Scripts\Activate.ps1  # Windows
# source .venv/bin/activate  # macOS/Linux

# Reinstall dependencies if needed
pip install -r requirements.txt
```

### Permission Errors (Windows PowerShell)
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

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
