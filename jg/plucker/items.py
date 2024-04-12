from scrapy import Field, Item


# See supported Apify formats at
# https://docs.apify.com/platform/actors/development/actor-definition/output-schema


class Job(Item):
    title = Field(required=True)
    posted_on = Field(required=True, apify_format="date")

    url = Field(required=True, apify_format="link")
    apply_url = Field(apify_format="link")

    company_name = Field(required=True)
    company_url = Field(apify_format="link")
    company_logo_urls = Field(apify_format="array")

    locations_raw = Field(apify_format="array")
    remote = Field(apify_format="boolean")
    employment_types = Field(apify_format="array")

    description_html = Field(required=True)

    source = Field(required=True)
    source_urls = Field(apify_format="array", required=True)


class ExchangeRate(Item):
    code = Field(required=True)
    rate = Field(required=True, apify_format="number")
