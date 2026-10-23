from datetime import date

import pytest
from scrapy import Item, Request, Spider

from tests.utils import is_storable_on_apify


@pytest.mark.parametrize(
    "cb_kwargs, expected",
    [
        ({"name": "facebook", "urls": ["https://example.com/"]}, True),
        ({"item": {"title": "Python vývojář(ka)"}}, True),
        ({"today": date(2025, 3, 18)}, False),
        ({"item": Item()}, False),
    ],
)
def test_is_storable_on_apify(cb_kwargs: dict, expected: bool):
    request = Request("https://example.com/", cb_kwargs=cb_kwargs)

    assert is_storable_on_apify(request, Spider("test")) is expected
