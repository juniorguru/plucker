from datetime import date
from pathlib import Path

import pytest
from scrapy.http.response.html import HtmlResponse

from jg.plucker.followers.spider import Spider


FIXTURES_DIR = Path(__file__).parent


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
    item = spider.parse_linkedin(response, today=date(2025, 3, 18))

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


def test_spider_parse_facebook():
    filename = "facebook.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_facebook(response, today=date(2025, 3, 18))

    assert item == {
        "date": date(2025, 3, 18),
        "name": "facebook",
        "count": 413,
    }


def test_spider_parse_facebook_personal():
    filename = "facebook_personal.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_facebook(
        response, today=date(2025, 3, 18), name="facebook_personal"
    )

    assert item == {
        "date": date(2025, 3, 18),
        "name": "facebook_personal",
        "count": 668,
    }


def test_spider_parse_instagram():
    filename = "instagram.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_instagram(response, today=date(2025, 3, 18))

    assert item == {
        "date": date(2025, 3, 18),
        "name": "instagram",
        "count": 652,
    }


def test_spider_parse_instagram_personal():
    filename = "instagram_personal.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider()
    item = spider.parse_instagram(
        response, today=date(2025, 3, 18), name="instagram_personal"
    )

    assert item == {
        "date": date(2025, 3, 18),
        "name": "instagram_personal",
        "count": 328,
    }
