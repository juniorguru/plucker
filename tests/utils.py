from apify.scrapy.requests import to_apify_request, to_scrapy_request
from scrapy import Request, Spider


def is_storable_on_apify(request: Request, spider: Spider) -> bool:
    """Whether Apify can store the request in its request queue and restore it

    Apify stores queued requests as JSON and drops those it can't serialize,
    e.g. if meta or cb_kwargs contain dates or Scrapy items. Some values
    survive serialization, but change (tuples become lists, etc.).
    """
    if apify_request := to_apify_request(request, spider):
        return to_scrapy_request(apify_request, spider).cb_kwargs == request.cb_kwargs
    return False
