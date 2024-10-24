# Documentation: http://doc.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "Plucker"

LOG_LEVEL = "INFO"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "cs;q=0.8,en;q=0.6",
    "DNT": "1",
}

FAKEUSERAGENT_PROVIDERS = [
    "scrapy_fake_useragent.providers.FakeUserAgentProvider",
    "scrapy_fake_useragent.providers.FakerProvider",
    "scrapy_fake_useragent.providers.FixedUserAgentProvider",
]

USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 15_8_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.8 Mobile/15E148 DuckDuckGo/7 Safari/605.1.15"

ROBOTSTXT_OBEY = False

# If these occur, let's fail fast! For reference, see https://www.rfc-editor.org/rfc/rfc9110.html
HTTPERROR_ALLOWED_CODES = [400, 405, 406, 410, 411, 412, 413, 414, 415, 422, 501]

RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429, 999]

SPIDER_LOADER_CLASS = "jg.plucker.scrapers.SpiderLoader"

SPIDER_LOADER_SPIDERS_PATH = "./jg/plucker"

# Custom setting, see 'run_spider()' and 'raise_for_stats()'
SPIDER_MIN_ITEMS = 10

ITEM_PIPELINES = {
    "jg.plucker.pipelines.RequiredFieldsFilterPipeline": 50,
}

DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": None,
    "scrapy_fake_useragent.middleware.RandomUserAgentMiddleware": 400,
    "jg.plucker.scrapers.RetryMiddleware": 401,
}

CLOSESPIDER_ERRORCOUNT = 1

AUTOTHROTTLE_ENABLED = True

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

EXTENSIONS = {"scrapy.extensions.memusage.MemoryUsage": None}

FEEDS = {
    "items.json": {
        "format": "json",
        "encoding": "utf-8",
        "indent": 2,
        "overwrite": True,
    },
}
