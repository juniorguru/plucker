from pathlib import Path

import pytest
from langdetect import DetectorFactory
from scrapy import Spider

from juniorguru_plucker.items import Job
from juniorguru_plucker.pipelines.language_parser import Pipeline


DetectorFactory.seed = 0  # prevent non-deterministic language detection


fixtures = [
    pytest.param(path.read_text(), path.stem.split("_")[0], id=path.name)
    for path in (Path(__file__).parent).rglob("*.html")
]
assert len(fixtures) > 0, "No fixtures found"


@pytest.mark.parametrize("description_html, expected_lang", fixtures)
def test_language_parser(
    item: Job,
    spider: Spider,
    description_html: str,
    expected_lang: str,
):
    item["description_html"] = description_html
    item = Pipeline().process_item(item, spider)

    assert item["lang"] == expected_lang
