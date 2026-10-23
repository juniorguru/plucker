import asyncio
from pathlib import Path

import pytest
from scrapy import Request, signals
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler
from twisted.internet.error import TimeoutError
from twisted.python.failure import Failure

from jg.plucker.items import JobCheck
from jg.plucker.job_checks.spider import Spider
from jg.plucker.scrapers import StatsError


FIXTURES_DIR = Path(__file__).parent


@pytest.mark.parametrize(
    "status, expected_ok",
    [
        (200, True),
        (404, False),
        (410, False),
        (403, None),
        (500, None),
    ],
)
def test_spider_check_http(status: int, expected_ok: bool | None):
    url = "https://example.com/job/"
    response = TextResponse(
        "https://example.com/redirected/",
        status=status,
        request=Request(url, method="HEAD"),
    )
    links = list(Spider().check_http(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=expected_ok, reason=f"HTTP {status}")]


@pytest.mark.parametrize("status", [405, 501])
def test_spider_check_http_head_not_supported(status: int):
    url = "https://example.com/job/"
    response = TextResponse(url, status=status, request=Request(url, method="HEAD"))
    requests = list(Spider().check_http(response, urls=[url]))

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url == url
    assert requests[0].cb_kwargs == {"urls": [url]}
    assert requests[0].dont_filter is True


def test_spider_check_http_get_not_supported():
    url = "https://example.com/job/"
    response = TextResponse(url, status=405, request=Request(url, method="GET"))
    links = list(Spider().check_http(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=None, reason="HTTP 405")]


def test_spider_check_failure():
    urls = ["https://example.com/job1/", "https://example.com/job2/"]
    failure = Failure(TimeoutError())
    failure.request = Request("https://example.com/", cb_kwargs={"urls": urls})
    links = list(Spider().check_failure(failure))

    assert links == [
        JobCheck(url=urls[0], ok=None, reason="TimeoutError"),
        JobCheck(url=urls[1], ok=None, reason="TimeoutError"),
    ]


def test_spider_check_startupjobs_inconclusive():
    url = "https://www.startupjobs.cz/nabidka/81775/junior-software-administrator"
    response = TextResponse("https://example.com/feed.json", status=403)
    links = list(Spider().check_startupjobs(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=None, reason="STARTUPJOBS HTTP 403")]


def test_spider_check_startupjobs_unknown_id():
    url = "https://www.startupjobs.cz/startup/acme"
    response = TextResponse(
        "https://example.com/feed.json",
        body=Path(FIXTURES_DIR / "startupjobs.json").read_bytes(),
    )
    links = list(Spider().check_startupjobs(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=None, reason="STARTUPJOBS UNKNOWN ID")]


def test_spider_check_startupjobs():
    response = TextResponse(
        "https://example.com/feed.json",
        body=Path(FIXTURES_DIR / "startupjobs.json").read_bytes(),
    )
    links = list(
        Spider().check_startupjobs(
            response,
            urls=[
                "https://www.startupjobs.cz/nabidka/81775/junior-software-administrator-do-naseho-interniho-it-tymu",
                "https://www.startupjobs.cz/nabidka/82417/ict-engineer-se-zamerenim-na-linux-a-voip",
            ],
        )
    )

    assert links == [
        JobCheck(
            url="https://www.startupjobs.cz/nabidka/81775/junior-software-administrator-do-naseho-interniho-it-tymu",
            ok=False,
            reason="STARTUPJOBS",
        ),
        JobCheck(
            url="https://www.startupjobs.cz/nabidka/82417/ict-engineer-se-zamerenim-na-linux-a-voip",
            ok=True,
            reason="STARTUPJOBS",
        ),
    ]


@pytest.mark.parametrize(
    "stats_override",
    [
        {"log_count/ERROR": 0, "retry/max_reached": 1},  # shouldn't happen
        {"log_count/ERROR": 1, "retry/max_reached": 1},
        {"log_count/ERROR": 1, "retry/max_reached": 2},  # shouldn't happen
        {"log_count/ERROR": 3, "retry/max_reached": 3},
        {"log_count/ERROR": 40, "retry/max_reached": 40},
    ],
)
def test_evaluate_stats_passing(stats_override: dict):
    Spider.evaluate_stats(
        {
            "item_scraped_count": 10,
            "finish_reason": "finished",
            "item_dropped_reasons_count/MissingRequiredFields": 0,
            "spider_exceptions/count": 0,
            "log_count/ERROR": 0,
        }
        | stats_override,
        min_items=10,
    )


@pytest.mark.parametrize(
    "stats_override",
    [
        {"log_count/ERROR": 1},
        {"log_count/ERROR": 2, "retry/max_reached": 1},
        {"log_count/ERROR": 1, "spider_exceptions/count": 1},
    ],
)
def test_evaluate_stats_failing(stats_override: dict):
    with pytest.raises(StatsError):
        Spider.evaluate_stats(
            {
                "item_scraped_count": 10,
                "finish_reason": "finished",
                "item_dropped_reasons_count/MissingRequiredFields": 0,
                "spider_exceptions/count": 0,
                "log_count/ERROR": 0,
            }
            | stats_override,
            min_items=10,
        )


def test_spider_start_expects_links_to_be_assessed():
    urls = [
        "https://www.jobs.cz/rpd/2001440830/",
        "https://www.startupjobs.cz/nabidka/81775/junior-software-administrator",
        "https://cz.linkedin.com/jobs/view/tester-at-coolpeople-4015921370/",
    ]
    spider = Spider(links=[{"url": url} for url in urls])

    async def collect():
        return [request async for request in spider.start()]

    requests = asyncio.run(collect())

    assert spider._expected_urls == set(urls[:2])  # LinkedIn links are skipped
    assert all(request.dont_filter for request in requests)


def test_spider_from_crawler_tracks_scraped_items():
    url = "https://example.com/job/"
    crawler = get_crawler(Spider)
    spider = Spider.from_crawler(crawler, links=[{"url": url}])
    item = JobCheck(url=url, ok=True, reason="HTTP 200")

    crawler.signals.send_catch_log(signals.item_scraped, item=item, spider=spider)

    assert spider._assessed_urls == {url}


def test_spider_keeps_urls_as_given():
    urls = ["https://Example.com", "https://firma.cz/kariéra/vývojář"]
    spider = Spider(links=[{"url": url} for url in urls + urls])

    assert spider._start_urls == urls


def test_spider_rejects_invalid_urls():
    with pytest.raises(ValueError):
        Spider(links=[{"url": "not a URL"}])


def test_spider_logs_nothing_if_not_finished(caplog):
    url = "https://example.com/job/"
    spider = Spider(links=[{"url": url}])
    spider._expected_urls = {url}

    with caplog.at_level("ERROR"):
        spider.closed("shutdown")

    assert caplog.messages == []


def test_spider_logs_links_not_assessed(caplog):
    urls = ["https://example.com/job1/", "https://example.com/job2/"]
    spider = Spider(links=[{"url": url} for url in urls])
    spider._expected_urls = set(urls)
    spider.item_scraped(JobCheck(url=urls[0], ok=True, reason="HTTP 200"))

    with caplog.at_level("ERROR"):
        spider.closed("finished")

    assert caplog.messages == [f"Link not assessed: {urls[1]}"]


def jobs_cz_checks(*oks: bool | None) -> list[tuple[str, bool | None]]:
    return [(f"https://www.jobs.cz/rpd/{n}/", ok) for n, ok in enumerate(oks)]


@pytest.mark.parametrize(
    "checks, expected_messages",
    [
        pytest.param(
            jobs_cz_checks(None, None, None, None, None),
            ["Checks of jobs.cz don't work: 5/5 inconclusive"],
            id="all-inconclusive",
        ),
        pytest.param(
            jobs_cz_checks(None, None, None, True, False),
            ["Checks of jobs.cz don't work: 3/5 inconclusive"],
            id="mostly-inconclusive",
        ),
        pytest.param(
            jobs_cz_checks(None, None, True, True, False),
            [],
            id="minority-inconclusive",
        ),
        pytest.param(
            jobs_cz_checks(None, None, None, None),
            [],
            id="too-few-links",
        ),
        pytest.param(
            [
                ("https://www.jobs.cz/rpd/1/", None),
                ("https://jobs.cz/rpd/2/", None),
                ("https://www.jobs.cz/rpd/3/", None),
                ("https://jobs.cz/rpd/4/", None),
                ("https://www.jobs.cz/rpd/5/", None),
            ],
            ["Checks of jobs.cz don't work: 5/5 inconclusive"],
            id="with-and-without-www",
        ),
    ],
)
def test_spider_logs_sites_with_inconclusive_checks(
    caplog, checks: list[tuple[str, bool | None]], expected_messages: list[str]
):
    spider = Spider()
    for url, ok in checks:
        spider.item_scraped(JobCheck(url=url, ok=ok, reason="HTTP 403"))

    with caplog.at_level("ERROR"):
        spider.closed("finished")

    assert caplog.messages == expected_messages
