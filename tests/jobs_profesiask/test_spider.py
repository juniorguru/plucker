from datetime import date
from pathlib import Path
from typing import cast

import pytest
from scrapy.http.response.html import HtmlResponse

from jg.plucker.items import Job
from jg.plucker.jobs_profesiask.spider import (
    Spider,
    WAFChallengeError,
    clean_url,
    get_page,
    is_remote,
    parse_location,
    remove_remote,
)


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    url = "https://www.profesia.sk/praca/informacne-technologie/"
    response = HtmlResponse(url, body=Path(FIXTURES_DIR / "listing.html").read_bytes())
    requests = list(Spider().parse(response))

    assert len(requests) == 20 + 1  # jobs + next page

    assert requests[2].url == "https://www.profesia.sk/praca/grafton-slovakia/O5372759"
    job = requests[2].cb_kwargs["item"]
    assert sorted(job.keys()) == sorted(
        [
            "title",
            "company_name",
            "company_logo_urls",
            "locations_raw",
            "remote",
            "source",
            "source_urls",
        ]
    )
    assert job["source"] == "jobs-profesiask"
    assert job["title"] == "Software Developer – Application Platforms (Intapp)"
    assert job["company_name"] == "Grafton Slovakia s.r.o."
    assert job["company_logo_urls"] == [
        "https://profesiastatic.sk/images/top_logo/11247_Grafton240x100_new.png"
    ]
    assert job["locations_raw"] == ["Bratislava, Slovak Republic"]
    assert job["remote"] is False
    assert job["source_urls"] == [
        "https://www.profesia.sk/praca/grafton-slovakia/O5372759",
        url,
    ]

    assert (
        requests[-1].url
        == "https://www.profesia.sk/praca/informacne-technologie/?page_num=2"
    )


def test_spider_parse_without_logo():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/informacne-technologie/",
        body=Path(FIXTURES_DIR / "listing.html").read_bytes(),
    )
    job = next(Spider().parse(response)).cb_kwargs["item"]

    assert job["title"] == (
        "Product Owner pre optimalizácie interných IT služieb a UX, 100% z domu"
    )
    assert "company_logo_urls" not in job


def test_spider_parse_remote():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/informacne-technologie/",
        body=Path(FIXTURES_DIR / "listing.html").read_bytes(),
    )
    job = next(Spider().parse(response)).cb_kwargs["item"]

    assert job["remote"] is True
    assert job["locations_raw"] == []


def test_spider_parse_location_note():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/informacne-technologie/",
        body=Path(FIXTURES_DIR / "listing.html").read_bytes(),
    )
    requests = list(Spider().parse(response))[:-1]  # without next page
    jobs = [request.cb_kwargs["item"] for request in requests]

    assert jobs[6]["company_name"] == "EY – Ernst & Young"
    assert jobs[6]["locations_raw"] == ["Bratislava, Slovensko"]
    assert jobs[6]["remote"] is False


def test_spider_parse_listing_page_last():
    url = "https://www.profesia.sk/praca/informacne-technologie/?page_num=59"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / "listing_page_last.html").read_bytes()
    )
    requests = list(Spider().parse(response))

    assert len(requests) == 17 + 0  # jobs + next page
    assert requests[-1].url == "https://www.profesia.sk/praca/eset/O5355880"


def test_spider_parse_listing_empty():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/informacne-technologie/?page_num=60",
        body=Path(FIXTURES_DIR / "listing_empty.html").read_bytes(),
    )
    requests = list(Spider().parse(response))

    assert len(requests) == 0


def test_spider_parse_job_standard():
    url = "https://www.profesia.sk/praca/needle-recruitment/O5372781"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / "job_standard.html").read_bytes()
    )
    job = cast(Job, next(Spider().parse_job(response, Job())))

    assert sorted(job.keys()) == sorted(
        [
            "company_logo_urls",
            "description_html",
            "employment_types",
            "posted_on",
            "source_urls",
            "url",
        ]
    )
    assert job["url"] == url
    assert job["source_urls"] == [url]
    assert job["posted_on"] == date(2026, 10, 9)
    assert job["employment_types"] == ["plný úväzok"]
    assert job["company_logo_urls"] == [
        "https://public.profesia.sk/companies/262923/company_logo/12352/cropped.png?t=1753085491"
    ]
    assert job["description_html"].startswith(
        '<div class="details" itemprop="description">'
    )
    assert "<strong>Čo vás čaká:</strong>" in job["description_html"]
    assert "Požiadavky na zamestnanca" in job["description_html"]


def test_spider_parse_job_en():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/sourcefirst-international/O5302301",
        body=Path(FIXTURES_DIR / "job_en.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job())))

    assert job["employment_types"] == ["full-time"]


def test_spider_parse_job_custom():
    url = "https://www.profesia.sk/praca/softip/O5372508"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / "job_custom.html").read_bytes()
    )
    job = cast(Job, next(Spider().parse_job(response, Job())))

    assert sorted(job.keys()) == sorted(
        ["description_html", "posted_on", "source_urls", "url"]
    )
    assert job["posted_on"] == date(2026, 10, 9)
    assert job["description_html"].startswith('<div class="maintextearea">')
    assert "<h1>Head of Engineering - náš líder pre vývoj SW" in job["description_html"]
    assert "AI-native development" in job["description_html"]


def test_spider_parse_job_custom_microdata():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/grafton-slovakia/O5372759",
        body=Path(FIXTURES_DIR / "job_custom_microdata.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job())))

    assert job["employment_types"] == ["full-time"]
    assert job["description_html"].startswith('<div class="maintextearea">')


def test_spider_parse_job_keeps_card_data():
    item = Job(
        title="Software Developer",
        company_name="Grafton Slovakia s.r.o.",
        locations_raw=["Bratislava, Slovak Republic"],
        remote=False,
        source_urls=["https://www.profesia.sk/praca/informacne-technologie/"],
    )
    url = "https://www.profesia.sk/praca/grafton-slovakia/O5372759"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / "job_custom_microdata.html").read_bytes()
    )
    job = cast(Job, next(Spider().parse_job(response, item)))

    assert job["title"] == "Software Developer"
    assert job["locations_raw"] == ["Bratislava, Slovak Republic"]
    assert job["remote"] is False
    assert job["source_urls"] == [
        "https://www.profesia.sk/praca/grafton-slovakia/O5372759",
        "https://www.profesia.sk/praca/informacne-technologie/",
    ]


def test_spider_parse_waf_challenge():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/informacne-technologie/?page_num=3",
        status=202,
        headers={"x-amzn-waf-action": "challenge"},
        body=b"",
    )

    with pytest.raises(WAFChallengeError):
        list(Spider().parse(response))


def test_spider_parse_job_waf_challenge():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/softip/O5372508",
        status=202,
        headers={"x-amzn-waf-action": "challenge"},
        body=b"",
    )

    with pytest.raises(WAFChallengeError):
        list(Spider().parse_job(response, Job()))


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://www.profesia.sk/praca/eset/O5355880?search_id=b19eb08d-ac8a",
            "https://www.profesia.sk/praca/eset/O5355880",
        ),
        (
            "https://www.profesia.sk/praca/eset/O5355880",
            "https://www.profesia.sk/praca/eset/O5355880",
        ),
    ],
)
def test_clean_url(url: str, expected: str):
    assert clean_url(url) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.profesia.sk/praca/informacne-technologie/", 1),
        ("https://www.profesia.sk/praca/informacne-technologie/?page_num=2", 2),
        ("/praca/informacne-technologie/?page_num=59", 59),
    ],
)
def test_get_page(url: str, expected: int):
    assert get_page(url) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Bratislava", "Bratislava"),
        (
            "Bratislava, Slovensko (Pozícia umožňuje občasnú prácu z domu)",
            "Bratislava, Slovensko",
        ),
        (
            "Košice, Slovak Republic (Job with occasional home office)",
            "Košice, Slovak Republic",
        ),
        (
            "Prešovský kraj, Košický kraj (Práca vyžaduje cestovanie)",
            "Prešovský kraj, Košický kraj",
        ),
        ("Lenovo (Slovakia), Bratislava", "Lenovo (Slovakia), Bratislava"),
    ],
)
def test_parse_location(text: str, expected: str):
    assert parse_location(text) == expected


@pytest.mark.parametrize(
    "locations, expected",
    [
        (["Práca z domu"], True),
        (["Práce z domu"], True),
        (["Bratislava", "Práca z domu"], True),
        (["Bratislava"], False),
        ([], False),
    ],
)
def test_is_remote(locations: list[str], expected: bool):
    assert is_remote(locations) is expected


def test_remove_remote():
    assert remove_remote(["Bratislava", "Práca z domu"]) == ["Bratislava"]
