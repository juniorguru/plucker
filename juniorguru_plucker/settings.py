# Documentation: http://doc.scrapy.org/en/latest/topics/settings.html

BOT_NAME = "juniorguru_plucker"

LOG_LEVEL = "INFO"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

USER_AGENT = "JuniorGuruBot (+https://junior.guru)"

ROBOTSTXT_OBEY = False  # requesting APIs etc., so irrelevant, saving a few requests

SPIDER_LOADER_CLASS = "juniorguru_plucker.actors.SpiderLoader"

# ITEM_PIPELINES = {
#     # 'juniorguru_plucker.pipelines.TitleItemPipeline': 123,
# }

CLOSESPIDER_ERRORCOUNT = 1

CLOSESPIDER_TIMEOUT_NO_ITEM = 30  # seconds
