# http://doc.scrapy.org/en/latest/topics/settings.html


BOT_NAME = "juniorguru_plucker"

DEPTH_LIMIT = 1

LOG_LEVEL = "INFO"

# NEWSPIDER_MODULE = 'juniorguru_plucker.spiders'

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

USER_AGENT = "JuniorGuruBot (+https://junior.guru)"

ROBOTSTXT_OBEY = False  # requesting APIs etc., so irrelevant, saving a few requests

# SPIDER_MODULES = ['juniorguru_plucker.spiders']

# ITEM_PIPELINES = {
#     # 'juniorguru_plucker.pipelines.TitleItemPipeline': 123,
# }
