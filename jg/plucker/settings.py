# Documentation: http://doc.scrapy.org/en/latest/topics/settings.html

import os


BOT_NAME = "Plucker"

LOG_LEVEL = "INFO"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "cs;q=0.8,en;q=0.6",
    "DNT": "1",
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:136.0) Gecko/20100101 Firefox/136.0"

ROBOTSTXT_OBEY = False

# If these occur, let's fail fast! For reference, see https://www.rfc-editor.org/rfc/rfc9110.html
HTTPERROR_ALLOWED_CODES = [400, 405, 406, 410, 411, 412, 413, 414, 415, 422, 501]

RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 403, 408, 429, 999]

HTTPCACHE_ENABLED = True

HTTPCACHE_EXPIRATION_SECS = 43200  # 12 hours

SPIDER_LOADER_CLASS = "jg.plucker.scrapers.SpiderLoader"

SPIDER_LOADER_SPIDERS_PATH = "./jg/plucker"

# Custom setting, see 'run_spider()' and 'raise_for_stats()'
SPIDER_MIN_ITEMS = 10

ITEM_PIPELINES = {
    "jg.plucker.pipelines.RequiredFieldsFilterPipeline": 50,
}

CLOSESPIDER_ERRORCOUNT = 1

AUTOTHROTTLE_ENABLED = True

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

EXTENSIONS = {"scrapy.extensions.memusage.MemoryUsage": None}

LINKEDIN_USERNAME = os.getenv("LINKEDIN_USERNAME")

LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

FEEDS = {
    "items.json": {
        "format": "json",
        "encoding": "utf-8",
        "indent": 2,
        "overwrite": True,
    },
}
