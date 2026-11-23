import asyncio
from datetime import date
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.crawler import CrawlerRunner
from scrapy.http.response.html import HtmlResponse
from scrapy.utils.test import get_crawler

from jg.plucker.followers.spider import (
    Spider,
    get_domain,
    is_login_redirect,
    parse_facebook_description,
    parse_instagram_description,
)
from jg.plucker.scrapers import get_actor_settings
from tests.utils import is_storable_on_apify


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


def test_spider_start_requests_are_storable_on_apify():
    async def collect():
        return [request async for request in spider.start()]

    spider = Spider()
    requests = asyncio.run(collect())

    assert requests
    for request in requests:
        assert is_storable_on_apify(request, spider) is True


def test_spider_profile_requests_are_not_filtered():
    async def collect():
        return [request async for request in spider.start()]

    spider = Spider()
    requests = asyncio.run(collect())
    profile_requests = [
        request
        for request in requests
        if get_domain(request.url) in ("facebook.com", "instagram.com")
    ]

    assert len(profile_requests) == 4
    assert all(request.dont_filter for request in profile_requests)


def test_spider_keeps_impersonation_and_apify_proxy():
    runner = CrawlerRunner(get_actor_settings({"useApifyProxy": True}))
    crawler = runner.create_crawler(Spider)
    middlewares = crawler.settings["DOWNLOADER_MIDDLEWARES"]

    assert middlewares["scrapy_impersonate.RandomBrowserMiddleware"] == 1000
    assert middlewares["apify.scrapy.middlewares.ApifyHttpProxyMiddleware"] == 750


def test_spider_today_from_string():
    assert Spider(today="2025-03-18").today == date(2025, 3, 18)


def test_spider_parse_mastodon():
    filename = "mastodon.html"
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
    )
    spider = Spider(today=date(2025, 3, 18))
    item = spider.parse_mastodon(response)

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
    spider = Spider(today=date(2025, 3, 18))
    item = spider.parse_linkedin(response, name=name)

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
        ("facebook_new_wording.html", "facebook", 412),
        ("facebook_personal_new_wording.html", "facebook_personal", 666),
    ],
)
def test_spider_parse_facebook(filename: str, name: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
        request=Request(f"https://example.com/{filename}"),
    )
    spider = Spider(today=date(2025, 3, 18))
    items = list(spider.parse_facebook(response=response, name=name))

    assert items == [
        {
            "date": date(2025, 3, 18),
            "name": name,
            "count": expected_count,
        }
    ]


@pytest.mark.parametrize(
    "filename, name, expected_count",
    [
        ("instagram.html", "instagram", 643),
        ("instagram_personal.html", "instagram_personal", 324),
    ],
)
def test_spider_parse_instagram(filename: str, name: str, expected_count: int):
    response = HtmlResponse(
        f"https://example.com/{filename}",
        body=Path(FIXTURES_DIR / filename).read_bytes(),
        request=Request(f"https://example.com/{filename}"),
    )
    spider = Spider(today=date(2025, 3, 18))
    items = list(spider.parse_instagram(response=response, name=name))

    assert items == [
        {
            "date": date(2025, 3, 18),
            "name": name,
            "count": expected_count,
        }
    ]


def login_redirect_response(retry_times: int) -> HtmlResponse:
    request = Request(
        "https://www.facebook.com/?next=https%3A%2F%2Fwww.facebook.com%2Fhonzajavorek%2F&_rdr",
        cb_kwargs={"name": "facebook_personal"},
        meta={
            "retry_times": retry_times,
            "redirect_urls": [
                "https://www.facebook.com/honzajavorek/?__xts__=1",
                "https://m.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2Fhonzajavorek%2F",
            ],
        },
    )
    return HtmlResponse(request.url, body=b"<html></html>", request=request)


def test_spider_parse_facebook_login_redirect_retries():
    spider = Spider.from_crawler(get_crawler(Spider))
    response = login_redirect_response(retry_times=0)
    results = list(spider.parse_facebook(response, name="facebook_personal"))

    assert len(results) == 1
    request = results[0]
    assert isinstance(request, Request)
    assert request.url == "https://www.facebook.com/honzajavorek/?__xts__=1"
    assert request.cb_kwargs == {"name": "facebook_personal"}
    assert request.meta["retry_times"] == 1
    assert request.meta["dont_cache"] is True
    assert "redirect_urls" not in request.meta


def test_spider_parse_facebook_login_redirect_gives_up(caplog):
    spider = Spider.from_crawler(get_crawler(Spider))
    response = login_redirect_response(retry_times=1)
    results = list(spider.parse_facebook(response, name="facebook_personal"))

    assert results == []
    assert "Gave up retrying" in caplog.text
    assert caplog.records[-1].levelname == "ERROR"
    assert caplog.records[-1].name == "followers"


def test_spider_parse_instagram_not_found():
    response = HtmlResponse(
        "https://www.instagram.com/juniordotguru/",
        body=b"<html></html>",
        status=404,
        request=Request("https://www.instagram.com/juniordotguru/"),
    )
    spider = Spider()

    with pytest.raises(ValueError, match="404"):
        list(spider.parse_instagram(response, name="instagram"))


@pytest.mark.parametrize(
    "description, expected_count",
    [
        ("Junior Guru. 410 followers. Education website", 410),
        ("Junior Guru. 412 sledující. Vzdělávací web", 412),
    ],
)
def test_parse_facebook_description(description: str, expected_count: int):
    assert parse_facebook_description(description) == expected_count


def test_parse_facebook_description_unknown():
    with pytest.raises(ValueError):
        parse_facebook_description(
            "Honza Javorek. 665 位粉丝. https://honzajavorek.cz/"
        )


@pytest.mark.parametrize(
    "description, expected_count",
    [
        (
            "643 Followers, 10 Following, 147 Posts - See Instagram photos and videos from junior.guru (@juniordotguru)",
            643,
        ),
        (
            "Počet sledujících: 324, kolik sleduje: 5, 668 příspěvků – Mrkněte na fotky a videa od Honza Javorek (@honza.javorek) na Instagramu",
            324,
        ),
    ],
)
def test_parse_instagram_description(description: str, expected_count: int):
    assert parse_instagram_description(description) == expected_count


def test_parse_instagram_description_unknown():
    with pytest.raises(ValueError):
        parse_instagram_description("1,2K Followers, 10 Following, 147 Posts")


@pytest.mark.parametrize(
    "urls, expected",
    [
        (["https://www.facebook.com/juniordotguru"], False),
        (
            [
                "https://www.facebook.com/honzajavorek/",
                "https://m.facebook.com/login/?next=https%3A%2F%2Fwww.facebook.com%2F",
                "https://www.facebook.com/?next=https%3A%2F%2Fwww.facebook.com%2F",
            ],
            True,
        ),
        (["https://www.instagram.com/accounts/login/"], True),
        ([], False),
    ],
)
def test_is_login_redirect(urls: list[str], expected: bool):
    assert is_login_redirect(urls) is expected
