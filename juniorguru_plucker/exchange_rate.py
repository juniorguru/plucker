from scrapy import Field, Item


class ExchangeRate(Item):
    code = Field()
    rate = Field(apify_format='number')
