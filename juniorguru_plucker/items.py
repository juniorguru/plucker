from scrapy import Field, Item


class Job(Item):
    title = Field()
    first_seen_on = Field(apify_format='date')

    url = Field(apify_format='link')
    apply_url = Field(apify_format='link')

    company_name = Field()
    company_url = Field(apify_format='link')
    company_logo_urls = Field(apify_format='array')

    locations_raw = Field(apify_format='array')
    remote = Field(apify_format='boolean')
    employment_types = Field(apify_format='array')

    description_html = Field()

    source = Field()
    source_urls = Field(apify_format='array')


class ExchangeRate(Item):
    code = Field()
    rate = Field(apify_format='number')
