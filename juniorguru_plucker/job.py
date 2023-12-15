from scrapy import Field, Item


class Job(Item):
    title = Field()
    first_seen_on = Field()

    url = Field()
    apply_url = Field()

    company_name = Field()
    company_url = Field()
    company_logo_urls = Field()

    locations_raw = Field()
    remote = Field()
    employment_types = Field()

    description_html = Field()

    source = Field()
    source_urls = Field()
