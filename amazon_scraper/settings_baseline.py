"""
Baseline settings for local, proxy-free Amazon crawls.

Overlays the upstream project settings (``amazon_scraper.settings``) and:

* disables the ScrapeOps proxy / monitor / retry integrations, so no API key
  is required;
* restores Scrapy's own RetryMiddleware;
* applies a deliberately slow, single-threaded crawl profile suitable for
  running from a normal home/office connection without a proxy.

The upstream ScrapeOps configuration is left untouched in ``settings.py`` and
stays available for later runs.

Select this module with::

    SCRAPY_PROJECT=baseline scrapy crawl ...
"""

from amazon_scraper.settings import *  # noqa: F401,F403

# --- ScrapeOps off ---------------------------------------------------------
SCRAPEOPS_PROXY_ENABLED = False

EXTENSIONS = {
    'scrapeops_scrapy.extension.ScrapeOpsMonitor': None,
}

DOWNLOADER_MIDDLEWARES = {
    'scrapeops_scrapy.middleware.retry.RetryMiddleware': None,
    'scrapeops_scrapy_proxy_sdk.scrapeops_scrapy_proxy_sdk.ScrapeOpsScrapyProxySdk': None,
    # Re-enable Scrapy's stock retry middleware (upstream switched it off).
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 550,
}

# --- Conservative local crawl profile --------------------------------------
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1

DOWNLOAD_DELAY = 2.0
RANDOMIZE_DOWNLOAD_DELAY = True

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 20
AUTOTHROTTLE_TARGET_CONCURRENCY = 0.5

COOKIES_ENABLED = True

RETRY_TIMES = 2

DOWNLOAD_TIMEOUT = 30

# A single, ordinary desktop browser identity. This is not UA rotation: the
# stock "Scrapy/x.y" agent is rejected outright by Amazon, so one realistic
# static UA is the minimum needed to observe normal behaviour.
USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
)

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,'
              'image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    'Upgrade-Insecure-Requests': '1',
}

LOG_LEVEL = 'INFO'

FEED_EXPORT_ENCODING = 'utf-8'
