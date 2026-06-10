from datetime import date
from pathlib import Path

import pytest
from scrapy.http.response.html import HtmlResponse
from scrapy.http.response.text import TextResponse

from jg.plucker.followers.spider import Spider, get_domain


FIXTURES_DIR = Path(__file__).parent


@pytest.mark.parametrize(
    "url, expected_domain",
    [
        ("https://www.instagram.com/juniordotguru", "instagram.com"),
        ("https://www.linkedin.com/posts/some-activity", "linkedin.com"),
        ("https://mastodonczech.cz/@honzajavorek", "mastodonczech.cz"),
        ("https://example.com/facebook.html", "example.com"),
    ],
)
def test_get_domain(url: str, expected_domain: str):
    assert get_domain(url) == expected_domain


def test_spider_parse_mastodon():
    filename = "mastodon.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_mastodon(response, today=date(2025, 3, 18))

    assert item == {
        "date": date(2025, 3, 18),
        "name": "mastodon",
        "count": 322,
    }


@pytest.mark.parametrize(
    "filename, name, expected_count",
    [
        ("linkedin.html", "linkedin", 935),
        ("linkedin2.html", "linkedin", 935),
        ("linkedin_personal.html", "linkedin_personal", 4263),
    ],
)
def test_spider_parse_linkedin(filename: str, name: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_linkedin(response, today=date(2025, 3, 18), name=name)

    assert item == {
        "date": date(2025, 3, 18),
        "name": name,
        "count": expected_count,
    }


@pytest.mark.parametrize(
    "filename, name, expected_count",
    [
        ("facebook.html", "facebook", 413),
        ("facebook_personal.html", "facebook_personal", 668),
    ],
)
def test_spider_parse_facebook(filename: str, name: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_facebook(response=response, today=date(2025, 3, 18), name=name)

    assert item == {
        "date": date(2025, 3, 18),
        "name": name,
        "count": expected_count,
    }


@pytest.mark.parametrize(
    "filename, name, expected_count",
    [
        ("instagram.json", "instagram", 652),
        ("instagram_personal.json", "instagram_personal", 328),
    ],
)
def test_spider_parse_instagram(filename: str, name: str, expected_count: int):
    response = TextResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
        encoding="utf-8",
    )
    spider = Spider()
    item = spider.parse_instagram(response=response, today=date(2025, 3, 18), name=name)

    assert item == {
        "date": date(2025, 3, 18),
        "name": name,
        "count": expected_count,
    }
