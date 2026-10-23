from typing import Callable

import pytest
from apify.scrapy.requests import to_apify_request
from scrapy import Request, Spider


def _is_storable_on_apify(request: Request, spider: Spider) -> bool:
    """Whether Apify can store the request in its request queue

    Apify stores queued requests as JSON and drops those it can't serialize,
    e.g. if meta or cb_kwargs contain dates or Scrapy items.
    """
    return to_apify_request(request, spider) is not None


@pytest.fixture
def is_storable_on_apify() -> Callable[[Request, Spider], bool]:
    return _is_storable_on_apify
