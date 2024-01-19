from pathlib import Path

import pytest
from scrapy import Spider

from juniorguru_plucker.items import Job
from juniorguru_plucker.pipelines.broken_encoding_filter import (
    BrokenEncoding,
    Pipeline,
)


fixtures_raising = [
    pytest.param(path.read_text(), id=path.name)
    for path in (Path(__file__).parent).rglob("*.html")
    if path.name.startswith("raising")
]
assert len(fixtures_raising) > 0, "No fixtures found"


@pytest.mark.parametrize("description_html", fixtures_raising)
def test_broken_encoding_filter_raising(
    item: Job,
    spider: Spider,
    description_html: str,
):
    item["description_html"] = description_html

    with pytest.raises(BrokenEncoding):
        Pipeline().process_item(item, spider)


fixtures_passing = [
    pytest.param(path.read_text(), id=path.name)
    for path in (Path(__file__).parent).rglob("*.html")
    if path.name.startswith("passing")
]
assert len(fixtures_passing) > 0, "No fixtures found"


@pytest.mark.parametrize("description_html", fixtures_passing)
def test_broken_encoding_filter_passing(
    item: Job,
    spider: Spider,
    description_html: str,
):
    item["description_html"] = description_html

    Pipeline().process_item(item, spider)
