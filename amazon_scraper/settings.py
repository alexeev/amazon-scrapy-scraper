BOT_NAME = 'amazon_scraper'

SPIDER_MODULES = ['amazon_scraper.spiders']
NEWSPIDER_MODULE = 'amazon_scraper.spiders'

ROBOTSTXT_OBEY = False

# Scrapy 2.19 enables the RemoteControl extension by default, which serves an
# HTTP endpoint that executes code inside the running crawl process. Nothing
# in this project uses it, and the validated baseline never had it, so it
# stays off rather than silently widening what a crawl exposes.
REMOTE_CONTROL_ENABLED = False

SCRAPEOPS_API_KEY = 'ScrapeOps.io API-KEY-HERE'

SCRAPEOPS_PROXY_ENABLED = True
# SCRAPEOPS_PROXY_SETTINGS = {'country': 'us'}

# Add In The ScrapeOps Monitoring Extension
EXTENSIONS = {
'scrapeops_scrapy.extension.ScrapeOpsMonitor': 500, 
}

LOG_LEVEL = 'INFO'

DOWNLOADER_MIDDLEWARES = {

    ## ScrapeOps Monitor
    'scrapeops_scrapy.middleware.retry.RetryMiddleware': 550,
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
    
    ## Proxy Middleware
    'scrapeops_scrapy_proxy_sdk.scrapeops_scrapy_proxy_sdk.ScrapeOpsScrapyProxySdk': 725,
}

# Max Concurrency On ScrapeOps Proxy Free Plan is 1 thread
CONCURRENT_REQUESTS = 1 