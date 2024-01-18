from datetime import date
from pathlib import Path
from typing import Any

import pytest
from scrapy.http import HtmlResponse, XmlResponse

from juniorguru_plucker.jobs_weworkremotely.spider import Spider, parse_date


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "remote-programming-jobs.rss").read_bytes(),
    )
    requests = list(Spider().parse(response))

    assert len(requests) == 4

    data = requests[0].cb_kwargs["feed_data"]
    assert data["title"] == "10up: Senior UI Engineer"
    assert data["remote"] is True
    assert data["first_seen_on"] == date(2020, 10, 28)
    assert data["company_logo_urls"] == []
    assert "<li>Moderate PHP experience.</li>" in data["description_html"]

    data = requests[1].cb_kwargs["feed_data"]
    assert data["company_logo_urls"] == [
        "https://wwr-pro.s3.amazonaws.com/logos/0017/2713/logo.gif"
    ]


def test_spider_parse_job():
    feed_data = dict(remote=True)
    response = HtmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "job.html").read_bytes(),
    )
    jobs = list(Spider().parse_job(response, feed_data))

    assert len(jobs) == 1

    job = jobs[0]

    assert sorted(job.keys()) == sorted(
        [
            "title",
            "url",
            "company_name",
            "company_url",
            "employment_types",
            "first_seen_on",
            "description_html",
            "company_logo_urls",
            "remote",
            "locations_raw",
            "source",
            "source_urls",
        ]
    )
    assert job["title"] == "DevOps Engineer, Kubernetes, AWS/GCP"
    assert job["url"] == "https://example.com/example/"
    assert job["company_name"] == "Bluelight Consulting"
    assert job["company_url"] == "https://bluelight.co"
    assert job["remote"] is True
    assert job["first_seen_on"] == date(2020, 10, 20)
    assert job["company_logo_urls"] == [
        "https://we-work-remotely.imgix.net/logos/0017/2301/logo.gif?ixlib=rails-4.0.0&w=50&h=50&dpr=2&fit=fill&auto=compress"
    ]
    assert job["source"] == "jobs-weworkremotely"
    assert job["source_urls"] == ["https://example.com/example/"]
    assert "<li>Kubernetes Certificates</li>" in job["description_html"]


def test_spider_parse_job_no_image():
    response = HtmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "job_no_image.html").read_bytes(),
    )
    job = next(Spider().parse_job(response, {}))

    assert job.get("company_logo_urls") is None


def test_spider_parse_job_json_decode_error_gets_skipped():
    response = HtmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "job_json_decode_error.html").read_bytes(),
    )
    jobs = Spider().parse_job(response, {})

    with pytest.raises(StopIteration):
        next(jobs)


@pytest.mark.parametrize(
    "value, expected",
    [
        (("2024-01-02 13:53:45 UTC"), date(2024, 1, 2)),
        (None, None),
    ],
)
def test_parse_date(value: Any, expected: date | None):
    assert parse_date(value) == expected
