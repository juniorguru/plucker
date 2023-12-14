from scrapy import Field, Item


class Job(Item):
    title = Field(required=True)
    first_seen_on = Field(required=True)

    url = Field(required=True)
    apply_url = Field()

    company_name = Field(required=True)
    company_url = Field()
    company_logo_urls = Field()

    locations_raw = Field()
    remote = Field()
    employment_types = Field()

    description_html = Field(required=True)

    source = Field(required=True)
    source_urls = Field(required=True)
