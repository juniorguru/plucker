import asyncio
import json
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from scrapy import Request
from scrapy.exceptions import DontCloseSpider
from scrapy.http.response.html import HtmlResponse
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.python.failure import Failure

from jg.plucker.items import Job
from jg.plucker.jobs_profesiask.spider import (
    LISTING_URL,
    Card,
    RequestFailedError,
    Spider,
    UnexpectedMarkupError,
    WAFChallengeError,
    check_filters,
    clean_listing_url,
    clean_url,
    get_page,
    is_custom_logo_url,
    parse_company_name,
    parse_language,
    parse_location,
    parse_locations,
)
from jg.plucker.scrapers import StatsError


FIXTURES_DIR = Path(__file__).parent


def listing_response(fixture_basename: str, url: str = LISTING_URL) -> HtmlResponse:
    return HtmlResponse(url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes())


def job_response(
    fixture_basename: str, url: str = "https://www.profesia.sk/praca/softip/O5372508"
) -> HtmlResponse:
    return HtmlResponse(url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes())


def make_card(**kwargs) -> Card:
    return Card(
        **(
            {
                "url": "https://www.profesia.sk/praca/softip/O5372508",
                "title": "Head of Engineering",
                "company_name": "SOFTIP, a.s.",
                "company_logo_urls": [],
                "locations": ["Bratislava, Slovensko"],
                "listing_urls": {f"{LISTING_URL}plny-uvazok/"},
                "employment_types": {"plný úväzok"},
            }
            | kwargs
        )
    )


def test_spider_parse():
    requests = list(Spider().parse(listing_response("listing.html")))

    assert [(request.url, request.cb_kwargs) for request in requests] == [
        (f"{LISTING_URL}plny-uvazok/", {"employment_type": "plný úväzok"}),
        (f"{LISTING_URL}skrateny-uvazok/", {"employment_type": "skrátený úväzok"}),
        (f"{LISTING_URL}zivnost/", {"employment_type": "živnosť"}),
        (
            f"{LISTING_URL}na-dohodu-brigady/",
            {"employment_type": "na dohodu (brigády)"},
        ),
        (f"{LISTING_URL}internship-staz/", {"employment_type": "stáž"}),
        (f"{LISTING_URL}?remote_work=1", {"remote": True}),
        (f"{LISTING_URL}?remote_work=2", {"remote": True}),
    ]


def test_check_filters():
    check_filters(listing_response("listing.html"))


@pytest.mark.parametrize(
    "old, new",
    [
        (b"&#x2F;internship-staz&#x2F;", b"&#x2F;dobrovolnictvo&#x2F;"),
        (b"remote_work&#x3D;2", b"remote_work&#x3D;3"),
    ],
)
def test_check_filters_unexpected(old: bytes, new: bytes):
    body = Path(FIXTURES_DIR / "listing.html").read_bytes()
    assert old in body
    response = HtmlResponse(LISTING_URL, body=body.replace(old, new))

    with pytest.raises(UnexpectedMarkupError):
        check_filters(response)


def test_spider_parse_listing():
    spider = Spider()
    url = f"{LISTING_URL}plny-uvazok/"
    requests = list(
        spider.parse_listing(
            listing_response("listing.html", url), employment_type="plný úväzok"
        )
    )

    assert [(request.url, request.cb_kwargs) for request in requests] == [
        (
            "https://www.profesia.sk/praca/informacne-technologie/?page_num=2",
            {"employment_type": "plný úväzok", "remote": False},
        )
    ]
    assert len(spider._cards) == 20
    card = spider._cards["https://www.profesia.sk/praca/grafton-slovakia/O5372759"]
    assert card == Card(
        url="https://www.profesia.sk/praca/grafton-slovakia/O5372759",
        title="Software Developer – Application Platforms (Intapp)",
        company_name="Grafton Slovakia s.r.o.",
        company_logo_urls=[
            "https://profesiastatic.sk/images/top_logo/11247_Grafton240x100_new.png"
        ],
        locations=["Bratislava, Slovak Republic"],
        listing_urls={url},
        employment_types={"plný úväzok"},
        remote=False,
    )


def test_spider_parse_listing_merges_cards():
    spider = Spider()
    url = "https://www.profesia.sk/praca/grafton-slovakia/O5372759"
    list(
        spider.parse_listing(
            listing_response("listing.html", f"{LISTING_URL}plny-uvazok/"),
            employment_type="plný úväzok",
        )
    )
    list(
        spider.parse_listing(
            listing_response("listing.html", f"{LISTING_URL}zivnost/?page_num=3"),
            employment_type="živnosť",
        )
    )
    list(
        spider.parse_listing(
            listing_response("listing.html", f"{LISTING_URL}?remote_work=2"),
            remote=True,
        )
    )

    assert len(spider._cards) == 20
    assert spider._cards[url].employment_types == {"plný úväzok", "živnosť"}
    assert spider._cards[url].remote is True
    assert spider._cards[url].listing_urls == {
        f"{LISTING_URL}plny-uvazok/",
        f"{LISTING_URL}zivnost/",
        f"{LISTING_URL}?remote_work=2",
    }


def test_spider_parse_listing_page_last():
    spider = Spider()
    response = listing_response("listing_page_last.html", f"{LISTING_URL}?page_num=59")
    requests = list(spider.parse_listing(response, employment_type="plný úväzok"))

    assert requests == []
    assert len(spider._cards) == 17
    card = spider._cards[
        "https://www.profesia.sk/praca/creative-sites-platforma-pre-ambiciozne-e-shopy/O5356344"
    ]
    assert card.company_name == (
        "CREATIVE sites, s.r.o. | platforma pre ambiciózne e-shopy"
    )


def test_spider_parse_listing_empty():
    spider = Spider()
    response = listing_response("listing_empty.html", f"{LISTING_URL}?page_num=60")
    requests = list(spider.parse_listing(response, employment_type="plný úväzok"))

    assert requests == []
    assert spider._cards == {}


def test_spider_parse_job_standard():
    url = "https://www.profesia.sk/praca/needle-recruitment/O5372781"
    card = make_card(url=url, title="Product Owner", company_name="NEEDLE")
    job = cast(
        Job,
        next(
            Spider().parse_job(job_response("job_standard.html", url), card.to_dict())
        ),
    )

    assert job == Job(
        source="jobs-profesiask",
        url=url,
        title="Product Owner",
        company_name="NEEDLE",
        company_logo_urls=[
            "https://public.profesia.sk/companies/262923/company_logo/12352/cropped.png?t=1753085491"
        ],
        locations_raw=["Bratislava, Slovensko"],
        remote=False,
        employment_types=["plný úväzok"],
        source_urls=[f"{LISTING_URL}plny-uvazok/", url],
        posted_on=date(2026, 10, 9),
        description_html=job["description_html"],
    )
    assert job["description_html"].startswith(
        '<div class="details" itemprop="description">'
    )
    assert "<strong>Čo vás čaká:</strong>" in job["description_html"]
    assert "Požiadavky na zamestnanca" in job["description_html"]


def test_spider_parse_job_en():
    job = cast(
        Job,
        next(Spider().parse_job(job_response("job_en.html"), make_card().to_dict())),
    )

    assert job["description_html"].startswith(
        '<div class="details" itemprop="description">'
    )


def test_spider_parse_job_custom():
    job = cast(
        Job,
        next(
            Spider().parse_job(job_response("job_custom.html"), make_card().to_dict())
        ),
    )

    assert job["posted_on"] == date(2026, 10, 9)
    assert job["description_html"].startswith('<div class="maintextearea">')
    assert "<h1>Head of Engineering - náš líder pre vývoj SW" in job["description_html"]
    assert "AI-native development" in job["description_html"]
    assert "company_logo_urls" not in job


@pytest.mark.parametrize(
    "fixture_basename, expected",
    [
        (
            "job_custom_microdata.html",
            "https://www.profesia.sk/customdesigns/GraftonSlovakia/4/6/images/logo-grafton.png",
        ),
        (
            "job_custom_label_paragraph.html",
            "https://www.profesia.sk/customdesigns/Orange/6/4/images/logo.svg",
        ),
        (
            "job_custom_label_strong.html",
            "https://www.profesia.sk/customdesigns/Prohr/2/images/logo.png",
        ),
    ],
)
def test_spider_parse_job_custom_logo(fixture_basename: str, expected: str):
    job = cast(
        Job,
        next(Spider().parse_job(job_response(fixture_basename), make_card().to_dict())),
    )

    assert job["description_html"].startswith('<div class="maintextearea">')
    assert job["company_logo_urls"] == [expected]


def test_spider_parse_job_card_data():
    card = make_card(
        company_name="CREATIVE sites, s.r.o. | platforma pre ambiciózne e-shopy",
        company_logo_urls=["https://profesiastatic.sk/images/top_logo/creative.png"],
        locations=[
            "Práca z domu",
            "Bratislava, Slovensko (Pozícia umožňuje občasnú prácu z domu)",
        ],
        employment_types={"živnosť", "plný úväzok"},
        remote=True,
    )
    job = cast(
        Job, next(Spider().parse_job(job_response("job_custom.html"), card.to_dict()))
    )

    assert job["company_name"] == "CREATIVE sites, s.r.o."
    assert job["company_logo_urls"] == [
        "https://profesiastatic.sk/images/top_logo/creative.png"
    ]
    assert job["locations_raw"] == ["Bratislava, Slovensko"]
    assert job["remote"] is True
    assert job["employment_types"] == ["plný úväzok", "živnosť"]


def test_spider_parse_job_skips_other_languages():
    jobs = list(
        Spider().parse_job(
            job_response("job_custom_label_de.html"), make_card().to_dict()
        )
    )

    assert jobs == []


def test_spider_parse_job_no_description():
    body = Path(FIXTURES_DIR / "job_custom.html").read_bytes()
    body = body.replace(b'class="maintextearea"', b'class="something-else"')
    response = HtmlResponse("https://www.profesia.sk/praca/softip/O5372508", body=body)

    with pytest.raises(UnexpectedMarkupError):
        list(Spider().parse_job(response, make_card().to_dict()))


def test_spider_parse_job_no_date_posted():
    body = Path(FIXTURES_DIR / "job_custom.html").read_bytes()
    body = body.replace(b'itemprop="datePosted"', b'itemprop="somethingElse"')
    response = HtmlResponse("https://www.profesia.sk/praca/softip/O5372508", body=body)

    with pytest.raises(UnexpectedMarkupError):
        list(Spider().parse_job(response, make_card().to_dict()))


def test_spider_parse_waf_challenge():
    response = HtmlResponse(
        f"{LISTING_URL}?page_num=3",
        status=202,
        headers={"x-amzn-waf-action": "challenge"},
        body=b"",
    )

    with pytest.raises(WAFChallengeError):
        list(Spider().parse_listing(response))


def test_spider_parse_job_waf_captcha():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/softip/O5372508",
        status=405,
        body=b"<html><head><title>Human Verification</title></head></html>",
    )

    with pytest.raises(WAFChallengeError):
        list(Spider().parse_job(response, make_card().to_dict()))


def test_spider_parse_job_waf_challenge():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/softip/O5372508",
        status=202,
        headers={"x-amzn-waf-action": "challenge"},
        body=b"",
    )

    with pytest.raises(WAFChallengeError):
        list(Spider().parse_job(response, make_card().to_dict()))


@pytest.mark.parametrize(
    "fixture_basename, expected",
    [
        ("job_standard.html", "sk"),
        ("job_en.html", "en"),
        ("job_custom_label_de.html", "de"),
    ],
)
def test_parse_language(fixture_basename: str, expected: str):
    assert parse_language(job_response(fixture_basename)) == expected


def test_parse_language_missing():
    response = HtmlResponse(
        "https://www.profesia.sk/praca/softip/O5372508", body=b"<html></html>"
    )

    with pytest.raises(UnexpectedMarkupError):
        parse_language(response)


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
        (f"{LISTING_URL}zivnost/?page_num=3", f"{LISTING_URL}zivnost/"),
        (f"{LISTING_URL}?remote_work=1&page_num=3", f"{LISTING_URL}?remote_work=1"),
        (f"{LISTING_URL}?remote_work=1", f"{LISTING_URL}?remote_work=1"),
    ],
)
def test_clean_listing_url(url: str, expected: str):
    assert clean_listing_url(url) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        (LISTING_URL, 1),
        (f"{LISTING_URL}?page_num=2", 2),
        ("/praca/informacne-technologie/?remote_work=1&page_num=59", 59),
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
            "Brno, Česko (Pozice umožňuje občasnou práci z domu)",
            "Brno, Česko",
        ),
        (
            "Prešovský kraj, Košický kraj (Práca vyžaduje cestovanie)",
            "Prešovský kraj, Košický kraj",
        ),
        (
            "Slovak Republic, Hungary, Poland (The job requires travelling)",
            "Slovak Republic, Hungary, Poland",
        ),
        ("Lenovo (Slovakia), Bratislava", "Lenovo (Slovakia), Bratislava"),
    ],
)
def test_parse_location(text: str, expected: str):
    assert parse_location(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Bratislava, Slovensko (Die Position ermöglicht, gelegentlich von zu Hause aus zu arbeiten )",
        "Bratislava (Staré Mesto)",
    ],
)
def test_parse_location_unexpected_note(text: str):
    with pytest.raises(UnexpectedMarkupError):
        parse_location(text)


@pytest.mark.parametrize(
    "locations, expected",
    [
        (["Práca z domu"], []),
        (["Remote work"], []),
        (["Bratislava", "Práca z domu"], ["Bratislava"]),
        (["Bratislava"], ["Bratislava"]),
    ],
)
def test_parse_locations_remote(locations: list[str], expected: list[str]):
    assert parse_locations(locations, remote=True) == expected


def test_parse_locations_remote_but_not_remote():
    with pytest.raises(UnexpectedMarkupError):
        parse_locations(["Práca z domu"], remote=False)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("SOFTIP, a.s.", "SOFTIP, a.s."),
        (
            "CREATIVE sites, s.r.o. | platforma pre ambiciózne e-shopy",
            "CREATIVE sites, s.r.o.",
        ),
    ],
)
def test_parse_company_name(text: str, expected: str):
    assert parse_company_name(text) == expected


def test_parse_company_name_unexpected():
    with pytest.raises(UnexpectedMarkupError):
        parse_company_name("ACME | e-shops | since 1990")


@pytest.mark.parametrize(
    "url, expected",
    [
        ("/customdesigns/Prohr/2/images/logo.png", True),
        ("/customdesigns/Orange/6/4/images/logo.svg", True),
        ("/customdesigns/IkeaIndustry/2/3/images/logo-ikea.png", True),
        ("https://public.profesia.sk/companies/228800/custom-offer/logo.png", True),
        ("/customdesigns/Ernstyoung/3/4/images/logo-ey-white.png", False),
        ("/customdesigns/Softip/1/3/images/header.jpg", False),
        ("/customdesigns/Softip/1/3/images/icons/ico-10.svg", False),
    ],
)
def test_is_custom_logo_url(url: str, expected: bool):
    assert is_custom_logo_url(url) is expected


def test_spider_idle_fetches_jobs_once(caplog):
    spider = Spider()
    spider.crawler = Mock()
    card = make_card()
    card_without_types = make_card(
        url="https://www.profesia.sk/praca/softip/O1", employment_types=set()
    )
    spider._cards = {card.url: card, card_without_types.url: card_without_types}

    with pytest.raises(DontCloseSpider):
        spider.spider_idle()
    spider.spider_idle()  # no more cards, lets the spider close

    requests = [call.args[0] for call in spider.crawler.engine.crawl.call_args_list]
    assert [(request.url, request.cb_kwargs) for request in requests] == [
        (card.url, {"card": card.to_dict()})
    ]
    json.dumps(requests[0].cb_kwargs)  # Apify request queue needs JSON
    assert f"No employment types, skipping {card_without_types.url}" in caplog.text


def test_card_to_dict_roundtrip():
    card = make_card(employment_types={"živnosť", "plný úväzok"}, remote=True)
    data = card.to_dict()

    assert json.loads(json.dumps(data)) == data
    assert data["employment_types"] == ["plný úväzok", "živnosť"]
    assert Card.from_dict(data) == card


def test_spider_parse_job_skips_expired():
    body = (FIXTURES_DIR.parent / "job_checks" / "profesiask_expired.html").read_bytes()
    response = HtmlResponse(
        "https://www.profesia.sk/praca/talent-solutions/O4000000", body=body
    )

    assert list(Spider().parse_job(response, make_card().to_dict())) == []


def test_spider_request_failed():
    response = HtmlResponse(f"{LISTING_URL}zivnost/?page_num=2", status=403)
    failure = Failure(HttpError(response, "Ignoring non-200 response"))
    failure.request = Request(f"{LISTING_URL}zivnost/?page_num=2")

    with pytest.raises(RequestFailedError):
        Spider().request_failed(failure)


def test_spider_cache_ignores_retried_codes():
    settings = Spider.custom_settings

    assert set(settings["RETRY_HTTP_CODES"]) <= set(
        settings["HTTPCACHE_IGNORE_HTTP_CODES"]
    )


def test_spider_start():
    async def collect():
        return [request async for request in Spider().start()]

    requests = asyncio.run(collect())

    assert [request.url for request in requests] == [LISTING_URL]
    assert requests[0].errback is not None


def test_spider_parse_job_collects_unknown_location_notes():
    spider = Spider()
    card = make_card(locations=["Brno, Česko (Práce vyžaduje cestování)"])
    jobs = list(spider.parse_job(job_response("job_custom.html"), card.to_dict()))

    assert jobs == []
    assert spider._unknown_location_notes == {"Práce vyžaduje cestování"}


def test_spider_closed_reports_unknown_location_notes():
    spider = Spider()
    spider.crawler = Mock()
    spider._unknown_location_notes = {"Note B", "Note A"}
    spider.closed("finished")

    spider.crawler.stats.set_value.assert_called_once_with(
        "profesiask/unknown_location_notes", ["Note A", "Note B"]
    )


def test_spider_evaluate_stats_unknown_location_notes():
    stats = {
        "item_scraped_count": 1000,
        "finish_reason": "finished",
        "profesiask/unknown_location_notes": ["Práce vyžaduje cestování"],
    }

    with pytest.raises(StatsError, match="Práce vyžaduje cestování"):
        Spider.evaluate_stats(stats, min_items=10)


def test_spider_evaluate_stats_passing():
    Spider.evaluate_stats(
        {"item_scraped_count": 1000, "finish_reason": "finished"}, min_items=10
    )
