from datetime import date
from pathlib import Path

import pytest
from scrapy.http import XmlResponse

from jg.plucker.jobs_startupjobs.spider import (
    Spider,
    drop_remote,
)


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed.xml").read_bytes(),
    )
    jobs = list(Spider().parse(response))

    assert len(jobs) == 2

    job = jobs[0]

    assert sorted(job.keys()) == sorted(
        [
            "title",
            "url",
            "apply_url",
            "company_name",
            "locations_raw",
            "employment_types",
            "posted_on",
            "description_html",
            "company_logo_urls",
            "remote",
            "source",
            "source_urls",
        ]
    )
    assert (
        job["title"]
        == "My hledáme stále! Přidej se k nám do týmu jako junior linux admin"
    )
    assert (
        job["url"]
        == "https://www.startupjobs.cz/nabidka/22025/my-hledame-stale-pridej-se-k-nam-do-tymu-jako-junior-linux-admin"
    )
    assert (
        job["apply_url"]
        == "https://www.startupjobs.cz/nabidka/22025/my-hledame-stale-pridej-se-k-nam-do-tymu-jako-junior-linux-admin?utm_source=juniorguru&utm_medium=cpc&utm_campaign=juniorguru"
    )
    assert job["company_name"] == "Cloudinfrastack"
    assert job["locations_raw"] == ["Praha, Česko"]
    assert job["remote"] is False
    assert job["employment_types"] == ["Part-time", "Full-time"]
    assert job["posted_on"] == date(2020, 5, 5)
    assert job["company_logo_urls"] == [
        "https://www.startupjobs.cz/uploads/U56OHNIPVP54cloudinfrastack-fb-logo-180x180-1154411059762.png"
    ]
    assert job["source"] == "jobs-startupjobs"
    assert job["source_urls"] == ["https://example.com/example/"]
    assert "<p>Ahoj, baví tě Linux?" in job["description_html"]


def test_spider_parse_job_types():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_job_types.xml").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["employment_types"] == ["Full-time", "External collaboration"]


def test_spider_parse_html_entities():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_html_entities.xml").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["title"] == "Analytik&programátor Junior"
    assert job["company_name"] == "P&J Capital"


def test_spider_parse_cities():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_cities.xml").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["locations_raw"] == ["Praha, Česko", "Olomouc, Česko"]


def test_spider_parse_remote():
    response = XmlResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_remote.xml").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["employment_types"] == ["Part-time", "External collaboration"]
    assert job["remote"] is True


@pytest.mark.parametrize(
    "types,expected",
    [
        ([], []),
        (["full-time", "remote", "part-time"], ["full-time", "part-time"]),
        (["remote", "remote"], []),
        (["full-time", "part-time"], ["full-time", "part-time"]),
    ],
)
def test_drop_remote(types, expected):
    assert drop_remote(types) == expected
