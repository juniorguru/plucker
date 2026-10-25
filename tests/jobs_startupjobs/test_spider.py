from datetime import date
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import HtmlResponse, TextResponse

from jg.plucker.items import Job
from jg.plucker.jobs_startupjobs.spider import (
    Spider,
    drop_remote,
    is_invalid,
    select_logo_url,
)


FIXTURES_DIR = Path(__file__).parent


def parse_jobs(response: TextResponse) -> list[Job]:
    spider = Spider()
    jobs = []
    for item in spider.parse(response):
        if isinstance(item, Request):
            startup_response = HtmlResponse(
                item.url, body=b"<html></html>", request=item
            )
            jobs.extend(spider.parse_startup(startup_response, **item.cb_kwargs))
        else:
            jobs.append(item)
    return jobs


def test_spider_parse():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed.json").read_bytes(),
    )
    jobs = parse_jobs(response)

    assert len(jobs) == 5

    job = jobs[0]

    assert sorted(job.keys()) == sorted(
        [
            "title",
            "url",
            "company_name",
            "locations_raw",
            "employment_types",
            "posted_on",
            "description_html",
            "remote",
            "source",
            "source_urls",
        ]
    )
    assert job["title"] == "Medior PHP developer"
    assert (
        job["url"]
        == "https://www.startupjobs.cz/nabidka/96801/medior-php-developer?utm_source=juniorguru&utm_medium=cpc&utm_campaign=juniorguru"
    )
    assert job["company_name"] == "3IT úspěšný eshop s.r.o."
    assert job["locations_raw"] == ["Ostrava, Česko"]
    assert job["remote"] is False
    assert job["employment_types"] == ["Full-time"]
    assert job["posted_on"] == date(2025, 11, 5)
    assert "company_logo_urls" not in job
    assert job["source"] == "jobs-startupjobs"
    assert job["source_urls"] == ["https://example.com/example/"]
    assert (
        "<br>Tvoř e-shopy, které odbaví tisíce objednávek měsíčně"
        in job["description_html"]
    )


def test_spider_parse_cities():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_cities.json").read_bytes(),
    )
    job = parse_jobs(response)[0]

    assert job["locations_raw"] == ["Ostrava, Česko", "Olomouc, Česko"]


def test_spider_parse_job_types():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_job_types.json").read_bytes(),
    )
    job = parse_jobs(response)[0]

    assert job["employment_types"] == ["Full-time", "External collaboration"]
    assert job["remote"] is False


def test_spider_parse_remote():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_remote.json").read_bytes(),
    )
    job = parse_jobs(response)[0]

    assert job["employment_types"] == ["Full-time", "External collaboration"]
    assert job["remote"] is True


def test_spider_parse_skips_invalid_offers():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_invalid_offer.json").read_bytes(),
    )
    jobs = parse_jobs(response)

    assert len(jobs) == 16
    assert all(job.get("title") and job.get("description_html") for job in jobs)
    assert not any("106875" in job["url"] for job in jobs)


def test_spider_parse_requests_each_startup_once():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_invalid_offer.json").read_bytes(),
    )
    requests = list(Spider().parse(response))
    urls = [request.url for request in requests]

    assert all(isinstance(request, Request) for request in requests)
    assert len(urls) == len(set(urls))
    assert sum(len(request.cb_kwargs["offers"]) for request in requests) == 16


def test_spider_parse_startup():
    response = HtmlResponse(
        "https://www.startupjobs.cz/startup/air-bank-a-s-1",
        body=Path(FIXTURES_DIR / "startup.html").read_bytes(),
    )
    offer = {
        "position": "Developer",
        "url": "https://www.startupjobs.cz/nabidka/1/developer",
        "startup": "Air Bank a.s.",
        "startupLogo": "https://www.startupjobs.cz/uploads/2025/08/eb01aefe2378836a08ab2554d6bc61ab.png",
        "cities": ["Praha, Česko"],
        "jobtypes": ["Full-time"],
        "lastUpdate": "2025-11-05",
        "description": "<p>Hi</p>",
    }
    jobs = list(
        Spider().parse_startup(
            response, offers=[offer], feed_url="https://example.com/example/"
        )
    )

    assert len(jobs) == 1
    assert jobs[0]["company_logo_urls"] == [
        "https://assets.startupjobs.cz/LOGO/13035/eb01aefe2378836a08ab2554d6bc61ab.png"
    ]
    assert jobs[0]["source_urls"] == ["https://example.com/example/"]


@pytest.mark.parametrize(
    "feed_logo_url,expected",
    [
        (
            "https://www.startupjobs.cz/uploads/2025/08/eb01aefe2378836a08ab2554d6bc61ab.png",
            "https://assets.startupjobs.cz/LOGO/13035/eb01aefe2378836a08ab2554d6bc61ab.png",
        ),
        ("https://www.startupjobs.cz/uploads/2025/08/0c66d6d229700c7df91f.png", None),
        ("", None),
        (None, None),
    ],
)
def test_select_logo_url(feed_logo_url: str | None, expected: str | None):
    logo_urls = {
        "https://assets.startupjobs.cz/LOGO/13035/eb01aefe2378836a08ab2554d6bc61ab.png"
    }

    assert select_logo_url(logo_urls, feed_logo_url) == expected


@pytest.mark.parametrize(
    "offer,expected",
    [
        ({"position": "Dev", "description": "<p>Hi</p>"}, False),
        ({"position": "", "description": "<p>Hi</p>"}, True),
        ({"position": "Dev", "description": ""}, True),
        ({"position": "   ", "description": "<p>Hi</p>"}, True),
        ({"position": "Dev", "description": "   "}, True),
        ({"description": "<p>Hi</p>"}, True),
        ({"position": "Dev"}, True),
        ({"position": None, "description": "<p>Hi</p>"}, True),
        ({"position": "Dev", "description": None}, True),
        ({}, True),
    ],
)
def test_is_invalid(offer: dict, expected: bool):
    assert is_invalid(offer) is expected


@pytest.mark.parametrize(
    "types,expected",
    [
        ([], []),
        (["full-time", "remote", "part-time"], ["full-time", "part-time"]),
        (["remote", "remote"], []),
        (["full-time", "part-time"], ["full-time", "part-time"]),
    ],
)
def test_drop_remote(types: list[str], expected: list[str]):
    assert drop_remote(types) == expected
