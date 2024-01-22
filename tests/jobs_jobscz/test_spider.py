from datetime import date
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse

from juniorguru_plucker.items import Job
from juniorguru_plucker.jobs_jobscz.spider import Spider


FIXTURES_DIR = Path(__file__).parent


def test_spider_parse():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/prace/...",
        body=Path(FIXTURES_DIR / "listing.html").read_bytes(),
    )
    requests = list(Spider().parse(response))

    assert len(requests) == 30 + 4  # jobs + pagination (without page=1)

    assert (
        requests[1].url
        == "https://beta.www.jobs.cz/rpd/2000120375/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=228"
    )
    job = requests[1].cb_kwargs["item"]
    assert sorted(job.keys()) == sorted(
        [
            "title",
            "company_name",
            "locations_raw",
            "first_seen_on",
            "company_logo_urls",
            "source",
            "source_urls",
        ]
    )
    assert job["source"] == "jobs-jobscz"
    assert job["first_seen_on"] == date.today()
    assert job["title"] == "Python vývojář(ka)"
    assert job["company_name"] == "Alma Career Czechia"
    assert job["locations_raw"] == ["Praha – Libeň"]
    assert job["company_logo_urls"] == [
        "https://my.teamio.com/recruit/logo?id=51a7da20-9bc3-4ff3-abfd-98b1f8136b7d&v=1703670754031&width=180"
    ]
    assert set(job["source_urls"]) == {
        "https://beta.www.jobs.cz/prace/...",
        "https://beta.www.jobs.cz/rpd/2000120375/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=228",
    }

    assert (
        requests[30].url
        == "https://beta.www.jobs.cz/prace/programator/?profession%5B0%5D=201100249&page=2"
    )
    assert (
        requests[-1].url
        == "https://beta.www.jobs.cz/prace/programator/?profession%5B0%5D=201100249&page=5"
    )


def test_spider_parse_without_logo():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/prace/...",
        body=Path(FIXTURES_DIR / "listing.html").read_bytes(),
    )
    requests = list(Spider().parse(response))

    assert (
        requests[0].url
        == "https://beta.www.jobs.cz/rpd/2000133941/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=228"
    )
    assert "company_logo_urls" not in requests[0].cb_kwargs["item"]


def test_spider_parse_job_custom():
    response = HtmlResponse(
        "https://fio.jobs.cz/detail-pozice?r=detail&id=1615173381&rps=228&impressionId=ac8f8a52-70fe-4be5-b32e-9f6e6b1c2b23",
        body=Path(FIXTURES_DIR / "job_custom.html").read_bytes(),
    )
    jobs = list(Spider().parse_job(response, Job()))

    assert len(jobs) == 0


def test_spider_parse_job_standard():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/rpd/1613133866/?searchId=ac8f8a52-70fe-4be5-b32e-9f6e6b1c2b23&rps=228",
        body=Path(FIXTURES_DIR / "job_standard.html").read_bytes(),
    )
    job = next(Spider().parse_job(response, Job()))

    assert sorted(job.keys()) == sorted(
        ["employment_types", "description_html", "source_urls", "url"]
    )
    assert job["url"] == "https://beta.www.jobs.cz/rpd/1613133866/"
    assert job["employment_types"] == [
        "práce na plný úvazek",
        "práce na zkrácený úvazek",
    ]
    assert job["source_urls"] == [
        "https://beta.www.jobs.cz/rpd/1613133866/?searchId=ac8f8a52-70fe-4be5-b32e-9f6e6b1c2b23&rps=228"
    ]

    assert (
        '<p class="typography-body-large-text-regular mb-800">Baví Tě frontend? Máš cit pro to, aby byly aplikace'
        in job["description_html"]
    )
    assert "<strong>Co Ti nabídneme navíc:</strong>" in job["description_html"]


@pytest.mark.skip(reason="TODO rewrite after HTML changes")
def test_spider_parse_job_standard_en():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/rpd/1613133866/",
        body=Path(FIXTURES_DIR / "job_standard_en.html").read_bytes(),
    )
    job = next(Spider().parse_job(response, Job()))

    assert sorted(job.keys()) == sorted(
        ["employment_types", "description_html", "source_urls", "url"]
    )
    assert job["employment_types"] == ["full-time work", "part-time work"]

    assert "bezpilotních letounů UAV i antidronové" in job["description_html"]
    assert "<strong>Areas of Our Projects</strong>" in job["description_html"]


def test_spider_parse_job_company():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/2000134247/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233",
        body=Path(FIXTURES_DIR / "job_company.html").read_bytes(),
    )
    job = next(Spider().parse_job(response, Job()))

    assert sorted(job.keys()) == sorted(
        [
            "employment_types",
            "description_html",
            "source_urls",
            "url",
            "company_url",
            "company_logo_urls",
        ]
    )
    assert job["url"] == "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/2000134247/"
    assert job["employment_types"] == ["práce na plný úvazek"]
    assert job["source_urls"] == [
        "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/2000134247/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233"
    ]
    assert job["company_url"] == "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/"
    assert job["company_logo_urls"] == [
        "https://aeqqktywno.cloudimg.io/v7/_cpimg_prod_/7910630/db7f211a-59cc-11ec-87b6-0242ac11000c.png?width=200&tl_px=0,9&br_px=350,110"
    ]
    assert (
        "stovky tisíc zákazníků měsíčně.<br>Jsi iOS vývojář/ka"
        in job["description_html"]
    )


def test_spider_parse_job_company_en():
    response = HtmlResponse(
        "https://www.jobs.cz/fp/infosys-361226/2000119063/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233",
        body=Path(FIXTURES_DIR / "job_company_en.html").read_bytes(),
    )
    job = next(Spider().parse_job(response, Job()))

    assert sorted(job.keys()) == sorted(
        [
            "employment_types",
            "description_html",
            "source_urls",
            "url",
            "company_url",
            "company_logo_urls",
        ]
    )
    assert job["employment_types"] == ["full-time work"]
    assert (
        '<strong>Employee perks, benefits</strong></p><ul class="typography-body-large-text-regular"><li>Hybrid work model;'
        in job["description_html"]
    )
