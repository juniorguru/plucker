import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest
from scrapy.http import HtmlResponse, TextResponse

from jg.plucker.items import Job
from jg.plucker.jobs_jobscz.spider import Spider, select_widget


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
            "posted_on",
            "company_logo_urls",
            "source",
            "source_urls",
        ]
    )
    assert job["source"] == "jobs-jobscz"
    assert job["posted_on"] == date.today()
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
    request = next(Spider().parse(response))

    assert (
        request.url
        == "https://beta.www.jobs.cz/rpd/2000133941/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=228"
    )
    assert "company_logo_urls" not in request.cb_kwargs["item"]


def test_spider_parse_multiple_locations():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/prace/...",
        body=Path(FIXTURES_DIR / "listing_location.html").read_bytes(),
    )
    requests = list(Spider().parse(response))
    job = requests[8].cb_kwargs["item"]

    assert job["locations_raw"] == ["Zlín"]


def test_spider_parse_job_standard():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/rpd/1613133866/?searchId=ac8f8a52-70fe-4be5-b32e-9f6e6b1c2b23&rps=228",
        body=Path(FIXTURES_DIR / "job_standard.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job(), "123")))

    assert sorted(job.keys()) == sorted(
        ["employment_types", "description_html", "locations_raw", "source_urls", "url"]
    )
    assert job["url"] == "https://beta.www.jobs.cz/rpd/1613133866/"
    assert job["employment_types"] == [
        "práce na plný úvazek",
        "práce na zkrácený úvazek",
    ]
    assert job["locations_raw"] == ["Brno"]
    assert job["source_urls"] == [
        "https://beta.www.jobs.cz/rpd/1613133866/?searchId=ac8f8a52-70fe-4be5-b32e-9f6e6b1c2b23&rps=228"
    ]

    assert (
        '<p class="typography-body-large-text-regular mb-800">Baví Tě frontend? Máš cit pro to, aby byly aplikace'
        in job["description_html"]
    )
    assert "<strong>Co Ti nabídneme navíc:</strong>" in job["description_html"]


def test_spider_parse_job_en():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/rpd/2000130345/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233",
        body=Path(FIXTURES_DIR / "job_en.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job(), "123")))

    assert job["employment_types"] == ["full-time work"]


def test_spider_parse_job_multiple_locations():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/rpd/2000130345/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233",
        body=Path(FIXTURES_DIR / "job_location.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job(), "123")))

    assert sorted(job["locations_raw"]) == [
        "Horní náměstí 3, Vsetín",
        "Masarykova třída 936/50, Olomouc – Hodolany",
        "Stojanova 1336, Uherské Hradiště",
        "Vavrečkova 7074, Zlín",
    ]


def test_spider_parse_job_company():
    response = HtmlResponse(
        "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/2000134247/?searchId=868cde40-9065-4e83-83ce-2fe2fa38d529&rps=233",
        body=Path(FIXTURES_DIR / "job_company.html").read_bytes(),
    )
    job = cast(Job, next(Spider().parse_job(response, Job(), "123")))

    assert sorted(job.keys()) == sorted(
        [
            "employment_types",
            "description_html",
            "locations_raw",
            "source_urls",
            "url",
            "company_url",
            "company_logo_urls",
        ]
    )
    assert job["url"] == "https://beta.www.jobs.cz/fp/alza-cz-a-s-7910630/2000134247/"
    assert job["employment_types"] == ["práce na plný úvazek"]
    assert job["locations_raw"] == ["U Pergamenky 1522/2, Praha – Holešovice"]
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


def test_spider_parse_job_widget():
    response = HtmlResponse(
        "https://4value-group.jobs.cz/detail-pozice?r=detail&id=2000142365&rps=228&impressionId=2c2d92cc-aebc-4949-9758-81b1b299224d",
        body=Path(FIXTURES_DIR / "job_widget.html").read_bytes(),
    )
    request = next(Spider().parse_job(response, Job(), "123"))

    assert request.method == "POST"
    assert request.headers["Content-Type"] == b"application/json"
    assert (
        request.headers["X-Api-Key"]
        == b"77dd9cff31711f94a97698fda3ecec7d9a561a15db53cfec868bafd31c9befbb"
    )
    assert (
        request.cb_kwargs["item"]["url"]
        == "https://4value-group.jobs.cz/detail-pozice?r=detail&id=2000142365"
    )
    assert request.cb_kwargs["item"]["source_urls"] == [
        "https://4value-group.jobs.cz/detail-pozice?r=detail&id=2000142365&rps=228&impressionId=2c2d92cc-aebc-4949-9758-81b1b299224d"
    ]

    body = json.loads(request.body)

    assert body["variables"]["jobAdId"] == "2000142365"
    assert body["variables"]["rps"] == 228
    assert body["variables"]["impressionId"] == "2c2d92cc-aebc-4949-9758-81b1b299224d"
    assert body["variables"]["widgetId"] == "e4a614ae-b321-47bb-8a7a-9d771a086880"
    assert body["variables"]["host"] == "4value-group.jobs.cz"
    assert (
        body["variables"]["referer"]
        == "https://4value-group.jobs.cz/detail-pozice?r=detail&id=2000142365&rps=228&impressionId=2c2d92cc-aebc-4949-9758-81b1b299224d"
    )


def test_spider_parse_job_widget_script_request():
    response = HtmlResponse(
        "https://skoda-auto.jobs.cz/detail-pozice?r=detail&id=1632413478&rps=233&impressionId=24d42f33-4e37-4a12-98a8-892a30257708",
        body=Path(FIXTURES_DIR / "job_widget_script.html").read_bytes(),
    )
    request = next(Spider().parse_job(response, Job(), "123"))

    assert request.method == "GET"
    assert (
        request.url
        == "https://skoda-auto.jobs.cz/assets/js/script.min.js?av=afe813c9aef55a9c"
    )


def test_spider_parse_job_widget_script_request_when_multiple_script_urls_occur():
    response = HtmlResponse(
        "https://vyrabimeletadla.jobs.cz/detail-pozice?r=detail&id=1632704350&rps=233&impressionId=1e70f565-4237-4616-95c9-4d09cbcd638a",
        body=Path(FIXTURES_DIR / "job_widget_script_multiple.html").read_bytes(),
    )
    request = next(Spider().parse_job(response, Job(), "123"))

    assert request.method == "GET"
    assert (
        request.url
        == "https://vyrabimeletadla.jobs.cz/assets/js/script.min.js?av=631f88dbfae16e74"
    )


def test_spider_parse_job_widget_script_request_when_there_is_vendor_slug_in_its_url():
    response = HtmlResponse(
        "https://kdejinde.jobs.cz/detail-pozice?r=detail&id=1638374443&rps=233&impressionId=c0551249-e0e1-4690-9789-d638f4b824e7#fms",
        body=Path(FIXTURES_DIR / "job_widget_script_vendor.html").read_bytes(),
    )
    request = next(Spider().parse_job(response, Job(), "123"))

    assert request.method == "GET"
    assert (
        request.url
        == "https://kdejinde.jobs.cz/assets/js/kdejinde/script.min.js?av=b43d21177d40b0f3"
    )


def test_spider_parse_job_widget_script_response():
    html_url = "https://skoda-auto.jobs.cz/detail-pozice?r=detail&id=1632413478&rps=233&impressionId=24d42f33-4e37-4a12-98a8-892a30257708"
    response = TextResponse(
        "https://skoda-auto.jobs.cz/assets/js/script.min.js?av=afe813c9aef55a9c",
        body=Path(FIXTURES_DIR / "job_widget_script.js").read_bytes(),
    )
    request = next(
        Spider().parse_job_widget_script(response, html_url, Job(), [], "123")
    )

    assert request.method == "POST"
    assert request.headers["Content-Type"] == b"application/json"
    assert (
        request.headers["X-Api-Key"]
        == b"79b29ad58130f75778f8b9d041b789fdd7fc6b428d01ba27f3c1ca569ec39757"
    )
    assert (
        request.cb_kwargs["item"]["url"]
        == "https://skoda-auto.jobs.cz/detail-pozice?r=detail&id=1632413478"
    )
    assert request.cb_kwargs["item"]["source_urls"] == [
        "https://skoda-auto.jobs.cz/detail-pozice?r=detail&id=1632413478&rps=233&impressionId=24d42f33-4e37-4a12-98a8-892a30257708"
    ]

    body = json.loads(request.body)

    assert body["variables"]["jobAdId"] == "1632413478"
    assert body["variables"]["rps"] == 233
    assert body["variables"]["impressionId"] == "24d42f33-4e37-4a12-98a8-892a30257708"
    assert body["variables"]["widgetId"] == "e06a5b79-9c00-495c-9f0d-a0cf77001ef6"
    assert body["variables"]["host"] == "skoda-auto.jobs.cz"
    assert (
        body["variables"]["referer"]
        == "https://skoda-auto.jobs.cz/detail-pozice?r=detail&id=1632413478&rps=233&impressionId=24d42f33-4e37-4a12-98a8-892a30257708"
    )


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(path, id=path.name)
        for path in FIXTURES_DIR.rglob("job_widget_script*.js")
    ],
)
def test_spider_parse_job_widget_script_response_parsing_doesnt_raise(path: Path):
    html_url = (
        "https://foo.jobs.cz/detail-pozice?r=detail&id=123&rps=456&impressionId=789"
    )
    response = TextResponse(
        "https://foo.jobs.cz/assets/js/script.min.js", body=path.read_bytes()
    )
    requests = Spider().parse_job_widget_script(response, html_url, Job(), [], "123")

    assert next(requests)


def test_spider_parse_job_widget_api():
    response = TextResponse(
        "https://api.capybara.lmc.cz/api/graphql/widget",
        body=Path(FIXTURES_DIR / "job_widget_api.json").read_bytes(),
    )
    job = next(Spider().parse_job_widget_api(response, Job(), "123"))

    assert "<li>služební cesty v rámci EU</li>" in job["description_html"]
    assert job["posted_on"] == date(2024, 2, 6)
    assert set(job["locations_raw"]) == {
        "Praha, Hlavní město Praha, Česká republika",
        "Plzeň, Plzeňský, Česká republika",
    }
    assert job["employment_types"] == ["práce na plný úvazek"]


@pytest.mark.parametrize(
    "names, expected",
    [
        (["main", "recommend"], "main"),
        (["main-cs", "main-en"], "main-cs"),
        (["foo", "bar"], "foo"),
    ],
)
def test_select_widget(names: list[str], expected: str):
    assert select_widget(names) == expected
