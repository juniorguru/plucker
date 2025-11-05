from datetime import date
from pathlib import Path

import pytest
from scrapy.http import TextResponse

from jg.plucker.jobs_startupjobs.spider import Spider, drop_remote


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed.json").read_bytes(),
    )
    jobs = list(Spider().parse(response))

    assert len(jobs) == 5

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
    assert job["title"] == "Medior PHP developer"
    assert job["url"] == "https://www.startupjobs.cz/nabidka/96801/medior-php-developer"
    assert (
        job["apply_url"]
        == "https://www.startupjobs.cz/nabidka/96801/medior-php-developer?utm_source=juniorguru&utm_medium=cpc&utm_campaign=juniorguru"
    )
    assert job["company_name"] == "3IT úspěšný eshop s.r.o."
    assert job["locations_raw"] == ["Ostrava, Česko"]
    assert job["remote"] is False
    assert job["employment_types"] == ["Full-time"]
    assert job["posted_on"] == date(2025, 11, 5)
    assert job["company_logo_urls"] == [
        "https://www.startupjobs.cz/uploads/2025/09/0c66d6d229700c7df91f059eabdec561.png"
    ]
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
    job = next(Spider().parse(response))

    assert job["locations_raw"] == ["Ostrava, Česko", "Olomouc, Česko"]


def test_spider_parse_job_types():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_job_types.json").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["employment_types"] == ["Full-time", "External collaboration"]
    assert job["remote"] is False


def test_spider_parse_remote():
    response = TextResponse(
        "https://example.com/example/",
        body=Path(FIXTURES_DIR / "feed_remote.json").read_bytes(),
    )
    job = next(Spider().parse(response))

    assert job["employment_types"] == ["Full-time", "External collaboration"]
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
def test_drop_remote(types: list[str], expected: list[str]):
    assert drop_remote(types) == expected
