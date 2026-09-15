"""Amazon search -> pagination -> product detail page crawler.

The crawl flow -- search, pagination, ASIN discovery, de-duplication, challenge
detection, pacing -- is unchanged from the validated baseline. Two layers were
added around it without touching it.

PDP parsing delegates to :mod:`amazon_scraper.extraction`, which returns a rich
record and reports per block whether the data was present, absent or failed to
parse.

Everything a crawl knows about itself now survives it (:mod:`amazon_scraper.run`):
the run's identity and locale travel on every record, every sighting is written
down *before* de-duplication can discard it, and the page each record came from
is kept so a later extractor never has to ask Amazon twice.
"""

import collections
import re
from urllib.parse import unquote, urlencode, urlparse

import scrapy
from scrapy import signals

from amazon_scraper.extraction.marketplaces import for_domain
from amazon_scraper.extraction.pdp import PdpExtractor
from amazon_scraper.extraction.text import clean, decode_entities
from amazon_scraper.run import DEFAULT_RUN_ROOT, CrawlRun, acquisition_locale

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

# The actual result list, as opposed to everything shaped like a result tile.
# Measured on a live amazon.de search page: the spider's discovery selector
# matches 82 nodes, of which 60 are the result grid and 22 are carousels and
# ad slots, 12 of them with an empty data-asin. Rank among the grid is the
# number that means "where a shopper saw it"; the other index is kept as-is so
# discovery behaviour does not change.
RESULT_GRID_CSS = 'div[data-component-type="s-search-result"]'

# Sponsored placement. All three markers agreed on all 60 grid items of the
# page they were measured on, so any one of them is enough and disagreement is
# worth recording rather than resolving.
SPONSORED_MARKERS = (
    ('ad_holder', lambda node: 'AdHolder' in (node.attrib.get('class') or '')),
    ('sponsored_label', lambda node: bool(node.css('[class*="sponsored-label"]'))),
    ('sspa_link', lambda node: bool(node.css('a[href*="/sspa/click"]'))),
)

SEARCH_TITLE_CSS = ('[data-cy=title-recipe] h2 span::text', 'h2 span::text',
                    'h2 a span::text')
SEARCH_PRICE_CSS = ('.a-price .a-offscreen::text',)


def first_of(node, css_selectors):
    """Text of the first of `css_selectors` that matches inside `node`."""
    for css in css_selectors:
        value = node.css(css).get()
        if value and value.strip():
            return value
    return ''

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
    ('variation', lambda r: r['variation'].get('values_by_asin')),
    ('review_histogram', lambda r: r['reviews'].get('histogram_percent')),
    ('review_sample', lambda r: r['reviews'].get('sample')),
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
    crawled one at a time: :meth:`start` seeds a single search request and
    every further one is yielded from :meth:`advance_search` after the
    previous search response has been parsed, so only one search request is
    ever outstanding. That keeps the ``/s?`` request rate close to the
    pattern the baseline validated, independently of scheduler behaviour.
    """

    name = "amazon_product"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider.begin_run()
        crawler.signals.connect(spider.finish_run, signal=signals.spider_closed)
        return spider

    def __init__(self, keyword='spaghetti hartweizen', domain='www.amazon.de',
                 max_pages=2, max_products_per_query=0, keep_pages=1,
                 *args, **kwargs):
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

        self.profile = for_domain(host)
        self.extractor = PdpExtractor(self.profile)
        self.keep_pages = str(keep_pages).lower() not in ('0', 'false', 'no')
        self._queued_by_query = collections.Counter()
        self._seen_asins = set()
        self.run = None

    # -- run identity ------------------------------------------------------

    def begin_run(self):
        """Open this crawl's evidence directory, after checking the locale.

        The locale check is the one thing here that can stop a crawl. Asking
        amazon.de for English and then reading it with German label lists does
        not fail anywhere: it silently produces records with an empty
        ``attributes`` block beside a full ``raw_tables``, which looks like
        Amazon publishing less rather than like a misconfiguration.
        """
        locale = acquisition_locale(self.settings, self.profile)
        if locale['status'] == 'conflict':
            # A plain error, not CloseSpider: CloseSpider does not print its
            # own reason, and a misconfiguration nobody can read is barely
            # better than the silent under-extraction it is guarding against.
            raise ValueError(
                f"Accept-Language {locale['accept_language']!r} asks "
                f"{self.marketplace} for {locale['language']!r}, but its label "
                f"vocabulary is {locale['expected_language']!r}. Extraction "
                f"would under-report without failing. Fix "
                f"DEFAULT_REQUEST_HEADERS, or crawl a marketplace whose "
                f"profile matches.")
        if locale['status'] == 'unset':
            self.logger.warning(
                'No Accept-Language configured: %s will answer in its own '
                'default locale, which is not recorded as a choice. The '
                'validated profile sets it explicitly.', self.marketplace)

        self.run = CrawlRun(
            root=self.settings.get('RUN_STORE', DEFAULT_RUN_ROOT),
            spider=self.name,
            marketplace=self.marketplace,
            locale=locale,
            arguments={'keyword': self.keywords, 'domain': self.marketplace,
                       'max_pages': self.max_pages,
                       'max_products_per_query': self.max_per_query,
                       'keep_pages': self.keep_pages},
            keep_pages=self.keep_pages,
        ).open()
        self.logger.info('Run %s -> %s (locale %s, %s)', self.run.run_id,
                         self.run.directory, locale['language'],
                         locale['status'])

    def finish_run(self, spider, reason):
        if self.run is not None:
            self.run.close(stats=self.crawler.stats.get_stats(),
                           finish_reason=reason)
            self.logger.info(
                'Run %s: %s discovery occurrences, %s pages retained in %s',
                self.run.run_id, self.run.counts['discovery_occurrences'],
                self.run.counts['pages_saved'], self.run.directory)

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

    async def start(self):
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
        grid_rank = self.grid_ranks(response)
        tree = response.selector.root.getroottree()
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

            # Written down before anything can discard it. The same ASIN
            # legitimately appears more than once -- on one live search page
            # two ASINs appeared twice, each once organic and once sponsored --
            # and every de-duplication below this line destroys that fact.
            self.record_occurrence(product, asin=asin, keyword=keyword,
                                   page=page, position=position,
                                   grid_position=grid_rank.get(
                                       tree.getpath(product.root)))

            if asin in self._seen_asins:
                stats.inc_value('amazon/discovery/repeat_sighting')
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

    @staticmethod
    def grid_ranks(response):
        """``{element path: rank}`` for the real result grid.

        The discovery selector deliberately stays as it was, so what gets
        crawled does not change. But its index counts carousels and empty ad
        tiles too, which is why "position 1" was missing from every query in
        the last validation run. The grid rank is the one a shopper would
        recognise; both are recorded and neither is guessed at.

        Keyed by tree path rather than by ``id()``: lxml creates an element
        proxy on demand and frees it once nothing refers to it, so proxy ids
        get recycled and would silently match the wrong result. (The same trap
        is documented in :func:`amazon_scraper.extraction.blocks.key_value_tables`.)
        It happens to be safe here only because the discovery list holds every
        proxy alive, which is an invariant nobody should have to preserve.
        """
        tree = response.selector.root.getroottree()
        return {tree.getpath(node.root): rank for rank, node
                in enumerate(response.css(RESULT_GRID_CSS), start=1)}

    @staticmethod
    def sponsored_markers(product):
        """Which sponsorship markers this result carries, if any."""
        return [name for name, test in SPONSORED_MARKERS if test(product)]

    def record_occurrence(self, product, asin, keyword, page, position,
                          grid_position):
        """Write one sighting to the run's discovery log."""
        if self.run is None:
            return
        markers = self.sponsored_markers(product)
        price_text = decode_entities(clean(
            first_of(product, SEARCH_PRICE_CSS)))
        self.run.record_discovery({
            'query': keyword,
            'search_page': page,
            'position': position,
            'grid_position': grid_position,
            'in_result_grid': grid_position is not None,
            'asin': asin,
            'sponsored': bool(markers),
            'sponsored_markers': markers,
            'result_title': clean(first_of(product, SEARCH_TITLE_CSS)),
            'result_price_text': price_text,
            'result_price_amount': self.profile.number(price_text),
            'product_url': self.product_url(asin),
        })
        self.crawler.stats.inc_value('amazon/discovery/occurrences')
        if markers:
            self.crawler.stats.inc_value('amazon/discovery/sponsored')

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

        asin = response.meta['asin']
        lineage = {
            'marketplace': self.marketplace,
            'asin': asin,
            'product_url': response.url,
            'canonical_url': response.css(
                'link[rel=canonical]::attr(href)').get() or response.url,
            'search_query': response.meta['search_query'],
            'search_page': response.meta['search_page'],
            'search_position': response.meta['search_position'],
        }
        if self.run is not None:
            # The run's identity and the locale that answered. A record whose
            # locale is unknown cannot be compared with one crawled in another.
            lineage.update(self.run.lineage())
            # Kept before the record is built, so a later extractor can be run
            # over this exact page without asking Amazon for it again.
            self.run.save_page(asin, response.text)

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
