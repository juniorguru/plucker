import json
import logging
from datetime import date
from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import TextResponse

from jg.plucker.items import Job
from jg.plucker.jobs_getjob.spider import (
    LISTING_PARAMS,
    REMOTE_LISTING_PARAMS,
    Spider,
    UnknownSourceError,
    get_apply_url,
    get_detail_url,
    get_employment_types,
    get_listing_url,
    get_skip_reason,
    has_description,
    has_next_page,
    load_job,
    parse_listing_jobs,
    text_to_html,
)
from jg.plucker.scrapers import UnexpectedDataError


FIXTURES_DIR = Path(__file__).parent


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def fixture_response(url: str, name: str, status: int = 200) -> TextResponse:
    return TextResponse(
        url,
        body=(FIXTURES_DIR / name).read_bytes(),
        status=status,
        request=Request(url),
    )


def listing_job(slug_suffix: str) -> dict:
    for job in load_fixture("listing.json")["nabidky"]:
        if job["slug"].endswith(slug_suffix):
            return job
    raise LookupError(slug_suffix)


def test_get_listing_url():
    assert get_listing_url(LISTING_PARAMS, 2) == (
        "https://getjob.cz/api/jobs/board?obor=IT+a+technologie&bezpripnuti=1&strana=2"
    )


def test_get_listing_url_remote():
    assert get_listing_url(REMOTE_LISTING_PARAMS, 1) == (
        "https://getjob.cz/api/jobs/board"
        "?obor=IT+a+technologie&bezpripnuti=1&ho=ano&strana=1"
    )


def test_get_detail_url():
    assert (
        get_detail_url("it-technik-482786834164")
        == "https://getjob.cz/api/jobs/board?nabidka=it-technik-482786834164"
    )


def test_parse_listing_jobs():
    jobs = parse_listing_jobs(load_fixture("listing.json"))

    assert len(jobs) == 6


def test_parse_listing_jobs_raises_on_unexpected_data():
    with pytest.raises(UnexpectedDataError):
        parse_listing_jobs({"error": "Something went wrong"})


@pytest.mark.parametrize(
    "fixture_name, expected",
    [
        ("listing.json", True),
        ("listing_remote.json", False),
    ],
)
def test_has_next_page(fixture_name: str, expected: bool):
    assert has_next_page(load_fixture(fixture_name)) is expected


def test_has_next_page_raises_on_unexpected_data():
    with pytest.raises(UnexpectedDataError):
        has_next_page({"nabidky": []})


@pytest.mark.parametrize(
    "slug_suffix, expected",
    [
        ("1ba729afb999", None),  # Úřad práce
        ("482786834164", None),  # Úřad práce
        ("e457a6b67e9a", "applied to on startupjobs.cz"),
        (
            "7640f51a30f6",
            "source 'careerjet': aggregator, the original source is unknown",
        ),
        ("abe7bcc58d1f", None),  # GetJob's own, apply link to the company's site
        ("e9d7a4fa4208", None),  # GetJob's own, apply by e-mail
    ],
)
def test_get_skip_reason(slug_suffix: str, expected: str | None):
    assert get_skip_reason(listing_job(slug_suffix)) == expected


def test_get_skip_reason_source_startupjobs():
    job = listing_job("e457a6b67e9a")
    job["reakce"] = {"typ": "email", "cil": "jobs@example.com"}

    assert get_skip_reason(job) == "source 'startupjobs': scraped by jobs-startupjobs"


@pytest.mark.parametrize(
    "apply_url, expected",
    [
        ("https://www.jobs.cz/rpd/2001234567/", "applied to on jobs.cz"),
        ("https://beta.www.jobs.cz/fp/abc/2001234567/", "applied to on jobs.cz"),
        ("https://www.profesia.sk/O1234567", "applied to on profesia.sk"),
        ("https://cz.linkedin.com/jobs/view/123", "applied to on linkedin.com"),
        ("https://startupjobs.cz/nabidka/1/developer", "applied to on startupjobs.cz"),
        ("https://www.notjobs.cz/careers/", None),
    ],
)
def test_get_skip_reason_domains(apply_url: str, expected: str | None):
    job = listing_job("abe7bcc58d1f")
    job["reakce"] = {"typ": "odkaz", "cil": apply_url}

    assert get_skip_reason(job) == expected


def test_get_skip_reason_unknown_source():
    job = listing_job("1ba729afb999")
    job["zdroj"] = {"kod": "jenjobs", "kind": "prevzato", "label": "přes JenJobs"}

    with pytest.raises(UnknownSourceError):
        get_skip_reason(job)


def test_get_skip_reason_unknown_kind_of_source():
    job = listing_job("1ba729afb999")
    job["zdroj"] = {"kod": "mpsv", "kind": "jiny", "label": "přes Úřad práce"}

    with pytest.raises(UnexpectedDataError):
        get_skip_reason(job)


def test_get_apply_url_link():
    assert (
        get_apply_url({"typ": "odkaz", "cil": "https://example.com/apply"})
        == "https://example.com/apply"
    )


def test_get_apply_url_email():
    assert get_apply_url({"typ": "email", "cil": "jobs@example.com"}) is None


def test_get_apply_url_unknown_type():
    with pytest.raises(UnexpectedDataError):
        get_apply_url({"typ": "formular", "cil": "https://example.com/apply"})


@pytest.mark.parametrize(
    "job_types, contract_types, expected",
    [
        (["fulltime"], ["smlouva"], ["plný úvazek"]),
        (
            ["parttime", "fulltime"],
            ["zivnost", "smlouva"],
            ["částečný úvazek", "plný úvazek", "živnost"],
        ),
        (["brigada"], ["dohoda"], ["brigáda", "dohoda"]),
        (["fulltime", "staz"], ["smlouva"], ["plný úvazek", "stáž"]),
        (["trainee"], [], ["trainee"]),
        ([], [], []),
    ],
)
def test_get_employment_types(
    job_types: list[str], contract_types: list[str], expected: list[str]
):
    assert get_employment_types(job_types, contract_types) == expected


@pytest.mark.parametrize(
    "job_types, contract_types",
    [
        (["neuvedeno"], []),
        ([], ["neuvedeno"]),
    ],
)
def test_get_employment_types_unknown(job_types: list[str], contract_types: list[str]):
    with pytest.raises(UnexpectedDataError):
        get_employment_types(job_types, contract_types)


def test_text_to_html():
    text = "Náplň práce:\n• vedení kurzu\n• nástup ihned\nPožadujeme:\n• znalost <HTML>"

    assert text_to_html(text) == (
        "<p>Náplň práce:</p>\n"
        "<ul><li>vedení kurzu</li><li>nástup ihned</li></ul>\n"
        "<p>Požadujeme:</p>\n"
        "<ul><li>znalost &lt;HTML&gt;</li></ul>"
    )


def test_text_to_html_bullets_on_separate_lines():
    text = "Náplň práce:\n•\nspráva PC,\n•\ninstalace SW.\nPožadujeme:"

    assert text_to_html(text) == (
        "<p>Náplň práce:</p>\n"
        "<ul><li>správa PC,</li><li>instalace SW.</li></ul>\n"
        "<p>Požadujeme:</p>"
    )


def test_text_to_html_blank_lines():
    assert text_to_html("Hello\n\n  \nWorld\n") == "<p>Hello</p>\n<p>World</p>"


def test_text_to_html_bullet_without_item():
    with pytest.raises(UnexpectedDataError):
        text_to_html("Náplň práce:\n•")


def test_load_job():
    job = load_job(
        load_fixture("detail_mpsv.json")["nabidka"],
        True,
        "jobs-getjob",
        "https://getjob.cz/api/jobs/board?nabidka=it-technik-482786834164",
    )

    assert sorted(job.keys()) == sorted(
        [
            "apply_url",
            "company_name",
            "description_html",
            "employment_types",
            "locations_raw",
            "posted_on",
            "remote",
            "source",
            "source_urls",
            "title",
            "url",
        ]
    )
    assert job["title"] == "IT technik"
    assert job["url"] == "https://getjob.cz/prace/it-technik-482786834164"
    assert (
        job["apply_url"]
        == "https://up.gov.cz/volna-mista-v-cr#/volna-mista-detail/67312987"
    )
    assert job["company_name"] == "JUHA s.r.o."
    assert job["locations_raw"] == ["Brno"]
    assert job["remote"] is True
    assert job["employment_types"] == ["částečný úvazek"]
    assert job["posted_on"] == date(2026, 11, 24)
    assert job["source"] == "jobs-getjob"
    assert job["source_urls"] == [
        "https://getjob.cz/api/jobs/board?nabidka=it-technik-482786834164"
    ]
    assert job["description_html"].startswith("<p>První kontakt osobně")
    assert (
        "<ul><li>správa PC, notebooků, tiskáren a další IT techniky,</li>"
        in (job["description_html"])
    )


def test_load_job_email():
    job = load_job(
        load_fixture("detail_email.json")["nabidka"],
        False,
        "jobs-getjob",
        "https://example.com",
    )

    assert "apply_url" not in job
    assert job["remote"] is False
    assert job["employment_types"] == ["brigáda", "dohoda"]
    assert job["posted_on"] == date(2026, 11, 6)


def test_load_job_without_location():
    data = load_fixture("detail_email.json")["nabidka"] | {"location": ""}
    job = load_job(data, False, "jobs-getjob", "https://example.com")

    assert "locations_raw" not in job


@pytest.mark.parametrize("company", ["", " "])
def test_load_job_without_company(company: str):
    data = load_fixture("detail_email.json")["nabidka"] | {"company": company}

    with pytest.raises(UnexpectedDataError):
        load_job(data, False, "jobs-getjob", "https://example.com")


@pytest.mark.parametrize(
    "description, expected",
    [
        ("Hledáme kolegu.", True),
        ("", False),
        (" \n ", False),
    ],
)
def test_has_description(description: str, expected: bool):
    data = load_fixture("detail_mpsv.json")["nabidka"] | {"popis": description}

    assert has_description(data) is expected


def test_spider_parse_remote_listing_last_page():
    spider = Spider()
    response = fixture_response(
        get_listing_url(REMOTE_LISTING_PARAMS, 1), "listing_remote.json"
    )
    requests = list(spider.parse_remote_listing(response, page=1))

    assert spider._remote_ids == {"8cefdd9e-cb82-4036-9569-973495d43228"}
    assert [request.url for request in requests] == [get_listing_url(LISTING_PARAMS, 1)]
    assert requests[0].callback == spider.parse


def test_spider_parse_remote_listing_next_page():
    spider = Spider()
    response = fixture_response(
        get_listing_url(REMOTE_LISTING_PARAMS, 1), "listing.json"
    )
    requests = list(spider.parse_remote_listing(response, page=1))

    assert [request.url for request in requests] == [
        get_listing_url(REMOTE_LISTING_PARAMS, 2)
    ]
    assert requests[0].cb_kwargs == {"page": 2}


def test_spider_parse():
    spider = Spider()
    spider._remote_ids = {"8cefdd9e-cb82-4036-9569-973495d43228"}
    response = fixture_response(get_listing_url(LISTING_PARAMS, 1), "listing.json")
    requests = list(spider.parse(response, page=1))

    assert [(request.url, request.cb_kwargs) for request in requests] == [
        (
            get_detail_url("tester-testerka-mobilnich-telefonu-na-dpp-1ba729afb999"),
            {"remote": False},
        ),
        (get_detail_url("it-technik-482786834164"), {"remote": True}),
        (
            get_detail_url(
                "digital-marketing-strategist-pro-mobilni-aplikace-abe7bcc58d1f"
            ),
            {"remote": False},
        ),
        (
            get_detail_url(
                "lektor-ka-pripravneho-kurzu-matematiky-na-prijimaci-zkousky-e9d7a4fa4208"
            ),
            {"remote": False},
        ),
        (get_listing_url(LISTING_PARAMS, 2), {"page": 2}),
    ]


def test_spider_parse_unknown_source(caplog: pytest.LogCaptureFixture):
    data = load_fixture("listing.json")
    data["nabidky"][0]["zdroj"] = {
        "kod": "jenjobs",
        "kind": "prevzato",
        "label": "přes JenJobs",
    }
    url = get_listing_url(LISTING_PARAMS, 1)
    response = TextResponse(
        url,
        body=json.dumps(data).encode(),
        request=Request(url),
    )
    with caplog.at_level(logging.ERROR, logger="jobs-getjob"):
        requests = list(Spider().parse(response, page=1))

    assert [request.url for request in requests] == [
        get_detail_url("it-technik-482786834164"),
        get_detail_url(
            "digital-marketing-strategist-pro-mobilni-aplikace-abe7bcc58d1f"
        ),
        get_detail_url(
            "lektor-ka-pripravneho-kurzu-matematiky-na-prijimaci-zkousky-e9d7a4fa4208"
        ),
        get_listing_url(LISTING_PARAMS, 2),
    ]
    assert [record.getMessage() for record in caplog.records] == [
        (
            "Unknown source 'jenjobs', skipping "
            "'tester-testerka-mobilnich-telefonu-na-dpp-1ba729afb999'"
        )
    ]


def test_spider_parse_job():
    spider = Spider()
    url = get_detail_url("it-technik-482786834164")
    jobs = list(
        spider.parse_job(fixture_response(url, "detail_mpsv.json"), remote=True)
    )

    assert len(jobs) == 1
    assert isinstance(jobs[0], Job)
    assert jobs[0]["source_urls"] == [url]


def test_spider_parse_job_gone():
    spider = Spider()
    response = TextResponse(
        get_detail_url("it-technik-482786834164"),
        body=b'{"error":"gone"}',
        status=410,
    )

    assert list(spider.parse_job(response, remote=True)) == []


def test_spider_parse_job_without_description():
    data = load_fixture("detail_mpsv.json")
    data["nabidka"]["popis"] = ""
    url = get_detail_url("it-technik-482786834164")
    response = TextResponse(url, body=json.dumps(data).encode(), request=Request(url))

    # Skipped by the spider, because the run fails on items dropped
    # by RequiredFieldsFilterPipeline, see evaluate_stats()
    assert list(Spider().parse_job(response, remote=True)) == []
