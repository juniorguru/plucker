from datetime import date
from pathlib import Path

import pytest
from scrapy.http.response.html import HtmlResponse

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
    "filename, expected_count",
    [
        ("linkedin.html", 935),
        ("linkedin2.html", 935),
    ],
)
def test_spider_parse_linkedin(filename: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_linkedin(response, today=date(2025, 3, 18), name="linkedin")

    assert item == {
        "date": date(2025, 3, 18),
        "name": "linkedin",
        "count": expected_count,
    }


def test_spider_parse_linkedin_personal():
    filename = "linkedin_personal.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_linkedin(
        response, today=date(2025, 3, 18), name="linkedin_personal"
    )

    assert item == {
        "date": date(2025, 3, 18),
        "name": "linkedin_personal",
        "count": 4263,
    }


@pytest.mark.parametrize(
    "filename, expected_count",
    [
        ("facebook.html", 413),
        ("facebook_personal.html", 668),
        ("instagram.html", 652),
        ("instagram_personal.html", 329),
    ],
)
def test_spider_parse_meta(filename: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    name = filename.removesuffix(".html")
    item = spider.parse_meta(response=response, today=date(2025, 3, 18), name=name)

    assert item == {
        "date": date(2025, 3, 18),
        "name": name,
        "count": expected_count,
    }
