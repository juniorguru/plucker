# Documentation: http://doc.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "juniorguru_plucker"

LOG_LEVEL = "INFO"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "cs;q=0.8,en;q=0.6",
    "DNT": "1",
}

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:123.0) Gecko/20100101 Firefox/123.0"

ROBOTSTXT_OBEY = False

# If these occur, let's fail fast!
# For reference, see https://www.rfc-editor.org/rfc/rfc9110.html
HTTPERROR_ALLOWED_CODES = [400, 405, 406, 410, 411, 412, 413, 414, 415, 422, 501, 999]

SPIDER_LOADER_CLASS = "juniorguru_plucker.actors.SpiderLoader"

SPIDER_LOADER_SPIDERS_PATH = "./juniorguru_plucker"

ITEM_PIPELINES = {
    "juniorguru_plucker.pipelines.RequiredFieldsFilterPipeline": 50,
}

CLOSESPIDER_ERRORCOUNT = 1

AUTOTHROTTLE_ENABLED = True
