from functools import cache

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
    source_urls = Field(required=True, apify_format="array")


class JobLogo(Item):
    image_url = Field(required=True, apify_format="image")
    original_image_url = Field(required=True, apify_format="image")
    width = Field(apify_format="number")
    height = Field(apify_format="number")
    format = Field(required=True, apify_format="string")
    source_url = Field(required=True, apify_format="link")


class JobCheck(Item):
    url = Field(required=True, apify_format="link")
    ok = Field(required=True, apify_format="boolean")
    reason = Field(required=True)


class ExchangeRate(Item):
    code = Field(required=True)
    rate = Field(required=True, apify_format="number")


class CourseProvider(Item):
    id = Field(required=True, apify_format="number")
    url = Field(required=True, apify_format="link")
    name = Field(required=True)
    description = Field(required=True)
    company_name = Field(required=True)
    business_id = Field(required=True, apify_format="number")


class Company(Item):
    name = Field(required=True)
    country_code = Field(required=True)
    business_id = Field(required=True, apify_format="number")
    legal_form = Field(required=True)
    years_in_business = Field(required=True, apify_format="number")


class Meetup(Item):
    title = Field(required=True)
    description = Field()
    starts_at = Field(required=True, apify_format="date")
    ends_at = Field(apify_format="date")
    location = Field()
    url = Field(required=True, apify_format="link")
    source_url = Field(required=True, apify_format="link")
    series_name = Field(required=True)
    series_org = Field(required=True)
    series_url = Field(required=True, apify_format="link")


class Followers(Item):
    date = Field(required=True, apify_format="date")
    name = Field(required=True)
    count = Field(required=True, apify_format="number")


@cache
def get_required_fields(item_class: type[Item]) -> set[str]:
    return {
        name
        for name, kwargs in item_class.fields.items()
        if kwargs.get("required") is True
    }


@cache
def get_image_fields(item_class: type[Item]) -> set[str]:
    return {
        name
        for name, kwargs in item_class.fields.items()
        if kwargs.get("apify_format") == "image"
    }
