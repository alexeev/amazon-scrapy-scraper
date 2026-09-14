import json
import re
from urllib.parse import unquote, urlencode, urlparse

import scrapy

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
    """Amazon search -> pagination -> product detail page crawler.

    All of keyword, marketplace and page limit are runtime arguments:

        scrapy crawl amazon_product \
            -a keyword="spaghetti hartweizen" \
            -a domain="www.amazon.de" \
            -a max_pages=2 \
            -O data/smoke_amazon_de.jsonl
    """

    name = "amazon_product"

    def __init__(self, keyword='spaghetti hartweizen', domain='www.amazon.de',
                 max_pages=2, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.keyword = keyword

        # Accept "amazon.de", "www.amazon.de" or "https://www.amazon.de/".
        host = domain.strip().rstrip('/')
        if '://' in host:
            host = urlparse(host).netloc
        self.marketplace = host
        self.base_url = f'https://{host}/'
        self.allowed_domains = [host]

        self.max_pages = max(1, int(max_pages))

    # -- URL construction (single source of truth for the marketplace) ------

    def search_url(self, page):
        query = urlencode({'k': self.keyword, 'page': page})
        return f'{self.base_url}s?{query}'

    def product_url(self, asin):
        return f'{self.base_url}dp/{asin}'

    # -- Crawl -------------------------------------------------------------

    def start_requests(self):
        yield scrapy.Request(
            url=self.search_url(1),
            callback=self.discover_product_urls,
            errback=self.handle_error,
            # Search pages ahead of product pages, so pagination is exercised
            # early even when the run is cut short by CLOSESPIDER_* limits.
            priority=10,
            meta={'search_page': 1},
        )

    def discover_product_urls(self, response):
        page = response.meta['search_page']
        stats = self.crawler.stats

        reason = challenge_reason(response)
        if reason:
            stats.inc_value('amazon/challenge/search')
            self.logger.warning(
                'CHALLENGE on search page %s (%s): %s', page, reason, response.url)
            return

        search_products = response.css("div.s-result-item[data-asin]")
        found = 0
        for product in search_products:
            asin = product.attrib.get('data-asin') or ''
            if not ASIN_RE.fullmatch(f'/dp/{asin}'):
                # Fall back to the link; sponsored results wrap the real
                # product URL inside a /sspa/click redirect.
                href = product.xpath('.//h2/ancestor::a[1]/@href').get() or ''
                match = ASIN_RE.search(unquote(href))
                if not match:
                    continue
                asin = match.group(1)

            found += 1
            yield scrapy.Request(
                url=self.product_url(asin),
                callback=self.parse_product_data,
                errback=self.handle_error,
                meta={'search_page': page, 'asin': asin},
            )

        stats.inc_value('amazon/search_pages_parsed')
        stats.inc_value('amazon/product_urls_discovered', found)
        self.logger.info('Search page %s: discovered %s product URLs', page, found)

        # Fan out the remaining search pages once, from page 1.
        if page == 1 and self.max_pages > 1:
            last_page = self.last_search_page(response)
            for page_num in range(2, min(self.max_pages, last_page) + 1):
                yield scrapy.Request(
                    url=self.search_url(page_num),
                    callback=self.discover_product_urls,
                    errback=self.handle_error,
                    priority=10,
                    meta={'search_page': page_num},
                )

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
        page = response.meta['search_page']
        asin = response.meta['asin']

        reason = challenge_reason(response)
        if reason:
            stats.inc_value('amazon/challenge/pdp')
            self.logger.warning('CHALLENGE on PDP %s (%s)', response.url, reason)
            return

        name = (response.css("#productTitle::text").get("") or "").strip()
        if not name:
            # 200 OK, not a challenge, but no product title: selector or page
            # structure problem, tracked separately from blocking.
            stats.inc_value('amazon/pdp_parse_failed')
            self.logger.warning('No #productTitle on %s', response.url)
            return

        try:
            image_data = json.loads(re.findall(
                r"colorImages':.*'initial':\s*(\[.+?\])},\n", response.text)[0])
        except (IndexError, json.JSONDecodeError):
            image_data = []

        variant_data = re.findall(
            r'dimensionValuesDisplayData"\s*:\s* ({.+?}),\n', response.text)

        feature_bullets = [
            bullet.strip()
            for bullet in response.css("#feature-bullets li ::text").getall()
            if bullet.strip()
        ]

        price_whole = response.css("span.a-price-whole::text").get()
        price_frac = response.css("span.a-price-fraction::text").get()
        price = f"{price_whole}.{price_frac}" if price_whole and price_frac \
            else price_whole or "N/A"

        rating = response.css("span.a-icon-alt::text").get()

        # amazon.de has no div[data-hook=total-review-count]; keep the .com
        # selector first and fall back to the element amazon.de does render.
        rating_count = (
            response.css("div[data-hook=total-review-count] ::text").get()
            or response.css("#acrCustomerReviewText::text").get("")
        ).strip()

        stats.inc_value('amazon/pdp_items')
        yield {
            # -- lineage -------------------------------------------------
            "search_query": self.keyword,
            "search_page": page,
            "marketplace": self.marketplace,
            "asin": asin,
            "product_url": response.url,
            # -- product data --------------------------------------------
            "name": name,
            "price": price,
            "stars": rating.strip() if rating else "",
            "rating_count": rating_count,
            "feature_bullets": feature_bullets,
            "images": image_data,
            "variant_data": variant_data,
        }

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
