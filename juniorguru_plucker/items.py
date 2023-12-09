from scrapy import Field, Item


class Job(Item):
    title = Field(required=True)
    first_seen_on = Field(required=True)
    lang = Field()

    url = Field(required=True)
    apply_url = Field()

    company_name = Field(required=True)
    company_url = Field()
    company_logo_urls = Field()
    company_logos = Field()
    company_logo_path = Field()

    locations_raw = Field()
    remote = Field()
    employment_types = Field()

    description_html = Field(required=True)

    source = Field(required=True)
    source_urls = Field(required=True)

    # def __repr__(self):
    #     return repr_item(self, ["title", "url", "apply_url", "source"])
