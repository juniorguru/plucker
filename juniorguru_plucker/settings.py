# Documentation: http://doc.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "juniorguru_plucker"

LOG_LEVEL = "INFO"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "cs;q=0.8,en;q=0.6",
}

USER_AGENT = f"{BOT_NAME} (+https://junior.guru)"

ROBOTSTXT_OBEY = False

SPIDER_LOADER_CLASS = "juniorguru_plucker.actors.SpiderLoader"

SPIDER_LOADER_SPIDERS_PATH = "./juniorguru_plucker"

ITEM_PIPELINES = {
    "juniorguru_plucker.pipelines.RequiredFieldsFilterPipeline": 50,
}

CLOSESPIDER_ERRORCOUNT = 1
