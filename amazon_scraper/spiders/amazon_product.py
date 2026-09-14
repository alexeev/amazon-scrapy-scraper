"""Amazon search -> pagination -> product detail page crawler.

The crawl flow (search, pagination, ASIN discovery, dedupe, challenge
detection) is unchanged from the validated baseline. What changed is the PDP
stage: instead of reading a handful of selectors inline, it delegates to
:mod:`amazon_scraper.extraction`, which returns a rich record and reports per
block whether the data was present, absent or failed to parse.
"""

import collections
import re
from urllib.parse import unquote, urlencode, urlparse

import scrapy

from amazon_scraper.extraction.marketplaces import for_domain
from amazon_scraper.extraction.pdp import PdpExtractor

# Markers that identify an Amazon anti-bot challenge ("Robot Check" / CAPTCHA)
# page. Amazon serves these with HTTP 200, so status alone proves nothing.
CHALLENGE_TEXT_MARKERS = (
    'enter the characters you see below',
    'geben sie die zeichen unten ein',
    'type the characters you see in this image',
    'to discuss automated access to amazon data',
    'api-services-support@amazon.com',
    'sorry, we just need to make sure you',
)

CHALLENGE_CSS_MARKERS = (
    'form[action*="validateCaptcha"]',
    '#captchacharacters',
    'img[src*="captcha"]',
)

ASIN_RE = re.compile(r'/(?:dp|gp/product)/([A-Z0-9]{10})')
BARE_ASIN_RE = re.compile(r'[A-Z0-9]{10}')

# Coverage counters emitted into the crawl stats, so a validation run reports
# extraction quality without a separate analysis pass. Each entry maps a stat
# suffix to a predicate over the finished record.
COVERAGE_CHECKS = (
    ('title', lambda r: r['title']),
    ('brand', lambda r: r['brand']),
    ('price', lambda r: r['price'].get('amount') is not None),
    ('unit_price', lambda r: r['unit_price'].get('amount') is not None),
    ('rating', lambda r: r['rating'].get('value') is not None),
    ('rating_count', lambda r: r['rating'].get('count') is not None),
    ('feature_bullets', lambda r: r['content']['feature_bullets']),
    ('description', lambda r: r['content']['description']),
    ('important_information', lambda r: r['content']['important_information']),
    ('aplus', lambda r: r['content']['aplus'].get('text')),
    ('ingredients', lambda r: r['food']['ingredients'].get('text')),
    ('allergens', lambda r: r['food']['allergens']),
    ('nutrition', lambda r: r['food']['nutrition'].get('per_100g')),
    ('nutrition_protein', lambda r: r['food']['nutrition']
        .get('per_100g', {}).get('protein_g') is not None),
    ('raw_tables', lambda r: r['raw_tables']),
    ('country_of_origin', lambda r: r['attributes'].get('country_of_origin')),
    ('total_quantity', lambda r: r['package'].get('total_quantity_base')),
    ('images', lambda r: r['media'].get('images')),
    ('breadcrumbs', lambda r: r['breadcrumbs']),
)


def challenge_reason(response):
    """Return a short reason string if `response` looks like an Amazon
    challenge/CAPTCHA page, otherwise None."""
    for css in CHALLENGE_CSS_MARKERS:
        if response.css(css):
            return 'captcha_form'

    title = (response.css('title::text').get() or '').strip().lower()
    if 'robot check' in title or 'amazon.com' == title:
        return 'robot_check_title'

    # Challenge pages are tiny compared to real Amazon pages; only scan the
    # text of small documents so we never substring-search a 2 MB PDP.
    if len(response.text) < 120_000:
        lowered = response.text.lower()
        for marker in CHALLENGE_TEXT_MARKERS:
            if marker in lowered:
                return 'challenge_text'

    return None


class AmazonProductSpider(scrapy.Spider):
    """Crawl Amazon search results and extract rich product detail records.

        scrapy crawl amazon_product \
            -a keyword="spaghetti hartweizen; penne rigate bio" \
            -a domain="www.amazon.de" \
            -a max_pages=2 \
            -O data/products.jsonl

    ``keyword`` accepts several queries separated by ``;``. Queries are
    crawled one at a time: only one search request is ever outstanding, which
    keeps the ``/s?`` request rate close to the pattern the baseline
    validated.
    """

    name = "amazon_product"

    def __init__(self, keyword='spaghetti hartweizen', domain='www.amazon.de',
                 max_pages=2, max_products_per_query=0, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.keywords = [k.strip() for k in str(keyword).split(';') if k.strip()]
        if not self.keywords:
            raise ValueError('keyword must contain at least one query')
        self.keyword = self.keywords[0]

        # Accept "amazon.de", "www.amazon.de" or "https://www.amazon.de/".
        host = domain.strip().rstrip('/')
        if '://' in host:
            host = urlparse(host).netloc
        self.marketplace = host
        self.base_url = f'https://{host}/'
        self.allowed_domains = [host]

        self.max_pages = max(1, int(max_pages))
        # 0 means "no cap". The cap is per query, so a broad first query
        # cannot starve the rest, and it stops PDP *discovery* rather than
        # cutting the crawl mid-record the way CLOSESPIDER_ITEMCOUNT does.
        self.max_per_query = max(0, int(max_products_per_query))

        self.extractor = PdpExtractor(for_domain(host))
        self._queued_by_query = collections.Counter()
        self._seen_asins = set()

    # -- URL construction (single source of truth for the marketplace) ------

    def search_url(self, keyword, page):
        query = urlencode({'k': keyword, 'page': page})
        return f'{self.base_url}s?{query}'

    def product_url(self, asin):
        return f'{self.base_url}dp/{asin}'

    def search_request(self, keyword_index, page):
        return scrapy.Request(
            url=self.search_url(self.keywords[keyword_index], page),
            callback=self.discover_product_urls,
            errback=self.handle_error,
            dont_filter=True,
            # Search pages ahead of product pages, so pagination is exercised
            # early even when the run is cut short by CLOSESPIDER_* limits.
            priority=10,
            meta={'search_page': page, 'keyword_index': keyword_index,
                  'search_query': self.keywords[keyword_index]},
        )

    # -- Crawl -------------------------------------------------------------

    def start_requests(self):
        yield self.search_request(0, 1)

    def discover_product_urls(self, response):
        page = response.meta['search_page']
        keyword_index = response.meta['keyword_index']
        keyword = response.meta['search_query']
        stats = self.crawler.stats

        reason = challenge_reason(response)
        if reason:
            stats.inc_value('amazon/challenge/search')
            self.logger.warning(
                'CHALLENGE on search page %s (%s): %s', page, reason, response.url)
            yield from self.advance_search(response, keyword_index, page)
            return

        search_products = response.css("div.s-result-item[data-asin]")
        found = 0
        for position, product in enumerate(search_products, start=1):
            asin = product.attrib.get('data-asin') or ''
            if not BARE_ASIN_RE.fullmatch(asin):
                # Fall back to the link; sponsored results wrap the real
                # product URL inside a /sspa/click redirect.
                href = product.xpath('.//h2/ancestor::a[1]/@href').get() or ''
                match = ASIN_RE.search(unquote(href))
                if not match:
                    continue
                asin = match.group(1)

            found += 1
            if asin in self._seen_asins:
                continue
            if self.query_budget_spent(keyword_index):
                continue
            self._seen_asins.add(asin)
            self._queued_by_query[keyword_index] += 1

            yield scrapy.Request(
                url=self.product_url(asin),
                callback=self.parse_product_data,
                errback=self.handle_error,
                meta={'search_page': page, 'asin': asin,
                      'search_query': keyword, 'search_position': position},
            )

        stats.inc_value('amazon/search_pages_parsed')
        stats.inc_value('amazon/product_urls_discovered', found)
        self.logger.info('Search page %s for %r: discovered %s product URLs',
                         page, keyword, found)

        yield from self.advance_search(response, keyword_index, page)

    def advance_search(self, response, keyword_index, page):
        """Issue the next search request, if any.

        Exactly one search request is outstanding at a time: the next page of
        the current query, or the first page of the next query. Amazon
        throttles bursts of ``/s?`` requests with HTTP 503 far more readily
        than it throttles PDP requests.
        """
        if self.query_budget_spent(keyword_index):
            # This query has all the products it was allowed; move on rather
            # than paginating further into it.
            if keyword_index + 1 < len(self.keywords):
                yield self.search_request(keyword_index + 1, 1)
            return

        last_page = min(self.max_pages, self.last_search_page(response)) \
            if page == 1 else self.max_pages
        if page < last_page:
            yield self.search_request(keyword_index, page + 1)
        elif keyword_index + 1 < len(self.keywords):
            yield self.search_request(keyword_index + 1, 1)

    def query_budget_spent(self, keyword_index):
        return bool(self.max_per_query) and \
            self._queued_by_query[keyword_index] >= self.max_per_query

    def last_search_page(self, response):
        """Highest numbered page offered by the pagination widget.

        Amazon.de mixes "Zurück"/"Weiter" labels into the same elements, so
        only numeric entries are considered.
        """
        labels = response.xpath(
            '//*[contains(@class, "s-pagination-item")]//text()'
        ).getall()
        numbers = [int(t.strip()) for t in labels if t.strip().isdigit()]
        return max(numbers) if numbers else 1

    def parse_product_data(self, response):
        stats = self.crawler.stats

        reason = challenge_reason(response)
        if reason:
            stats.inc_value('amazon/challenge/pdp')
            self.logger.warning('CHALLENGE on PDP %s (%s)', response.url, reason)
            return

        if not response.css('#productTitle, #title'):
            # 200 OK, not a challenge, but no product title: selector or page
            # structure problem, tracked separately from blocking.
            stats.inc_value('amazon/pdp_parse_failed')
            self.logger.warning('No #productTitle on %s', response.url)
            return

        lineage = {
            'marketplace': self.marketplace,
            'asin': response.meta['asin'],
            'product_url': response.url,
            'canonical_url': response.css(
                'link[rel=canonical]::attr(href)').get() or response.url,
            'search_query': response.meta['search_query'],
            'search_page': response.meta['search_page'],
            'search_position': response.meta['search_position'],
        }

        record = self.extractor.extract(response.selector, response.text, lineage)

        stats.inc_value('amazon/pdp_items')
        for name, check in COVERAGE_CHECKS:
            try:
                if check(record):
                    stats.inc_value(f'amazon/field/{name}')
            except Exception:  # a coverage counter must never break a record
                stats.inc_value(f'amazon/field_check_error/{name}')
        for error in record['extraction']['errors']:
            stats.inc_value(f'amazon/block_error/{error["block"]}')
        nutrition_source = record['food']['nutrition'].get('source')
        if nutrition_source:
            stats.inc_value(f'amazon/nutrition_source/{nutrition_source}')
        ingredients_source = record['food']['ingredients'].get('source')
        if ingredients_source:
            stats.inc_value(f'amazon/ingredients_source/{ingredients_source}')

        yield record

    def handle_error(self, failure):
        stats = self.crawler.stats
        response = getattr(failure.value, 'response', None)
        if response is not None:
            stats.inc_value('amazon/http_error')
            stats.inc_value(f'amazon/http_error/{response.status}')
            self.logger.warning('HTTP %s for %s', response.status, response.url)
        else:
            stats.inc_value('amazon/download_error')
            self.logger.warning('Download error for %s: %s',
                                failure.request.url, failure.value)
