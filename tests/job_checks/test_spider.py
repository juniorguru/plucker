import asyncio
from pathlib import Path

import pytest
from scrapy import Request, signals
from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.http import HtmlResponse, TextResponse
from scrapy.spidermiddlewares.httperror import HttpErrorMiddleware
from scrapy.utils.test import get_crawler
from twisted.internet.error import TimeoutError
from twisted.python.failure import Failure

from jg.plucker import settings
from jg.plucker.items import JobCheck
from jg.plucker.job_checks.spider import Spider, UnexpectedPageError, is_jobscz_url
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


@pytest.mark.parametrize(
    "response_url, fixture_basename, expected_reason",
    [
        (
            "https://www.jobs.cz/rpd/2001400333/",
            "jobscz_classic.html",
            "JOBSCZ HTTP 200 (classic)",
        ),
        (
            "https://beta.jobs.cz/nabidka/11c8f85d-3d13-41d1-a660-b65c4262d344/",
            "jobscz_beta.html",
            "JOBSCZ HTTP 200 (beta)",
        ),
        (
            "https://tatra.jobs.cz/detail-pozice?r=detail&id=2001459292&rps=0&impressionId=",
            "jobscz_widget.html",
            "JOBSCZ HTTP 200 (widget)",
        ),
        (
            "https://rb.jobs.cz/detail-pozice?r=detail&id=2001400311&rps=0&impressionId=",
            "jobscz_widget_assets.html",
            "JOBSCZ HTTP 200 (widget)",
        ),
    ],
)
def test_spider_check_jobscz_ok(
    response_url: str, fixture_basename: str, expected_reason: str
):
    url = "https://www.jobs.cz/rpd/2001400333/"
    response = HtmlResponse(
        response_url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )
    links = list(Spider().check_jobscz(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=True, reason=expected_reason)]


@pytest.mark.parametrize(
    "response_url, fixture_basename",
    [
        # the design of one site served at the other
        ("https://www.jobs.cz/rpd/2001400333/", "jobscz_beta.html"),
        ("https://beta.jobs.cz/nabidka/11c8f85d/", "jobscz_classic.html"),
        ("https://beta.jobs.cz/rpd/2001389794/", "jobscz_beta_404.html"),
        ("https://tatra.jobs.cz/detail-pozice?id=1", "jobscz_classic.html"),
    ],
)
def test_spider_check_jobscz_unexpected_page(response_url: str, fixture_basename: str):
    url = "https://www.jobs.cz/rpd/2001400333/"
    response = HtmlResponse(
        response_url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )

    with pytest.raises(UnexpectedPageError):
        list(Spider().check_jobscz(response, urls=[url]))


@pytest.mark.parametrize(
    "response_url, status, expected_ok",
    [
        ("https://www.jobs.cz/rpd/2000120375/", 404, False),
        ("https://www.jobs.cz/fp/smero-spol-s-r-o-5008768/2001400301/", 404, False),
        ("https://okin.jobs.cz/pd/2001400300/?rps=0&searchId=", 404, False),
        ("https://www.jobs.cz/rpd/2000120375/", 410, False),
        # beta.jobs.cz responds with 404 also to some live jobs
        ("https://beta.jobs.cz/rpd/2001389794/", 404, None),
        ("https://www.jobs.cz/rpd/2000120375/", 403, None),
        ("https://www.jobs.cz/rpd/2000120375/", 500, None),
    ],
)
def test_spider_check_jobscz_not_ok(
    response_url: str, status: int, expected_ok: bool | None
):
    url = "https://www.jobs.cz/rpd/2000120375/"
    response = HtmlResponse(
        response_url,
        status=status,
        body=Path(FIXTURES_DIR / "jobscz_beta_404.html").read_bytes(),
    )
    links = list(Spider().check_jobscz(response, urls=[url]))

    assert links == [JobCheck(url=url, ok=expected_ok, reason=f"JOBSCZ HTTP {status}")]


def test_spider_probe_jobscz_sets_classic_site_cookie():
    urls = ["https://www.jobs.cz/rpd/2001389794/", "https://abb.jobs.cz/pd/1/"]
    response = TextResponse(
        "https://www.jobs.cz/",
        status=302,
        headers=[
            ("Set-Cookie", "beta_bucket=5%3AA; path=/; domain=.jobs.cz"),
            ("Set-Cookie", "APJOBS72ID=a4f52830d497298d; path=/; HttpOnly"),
        ],
    )
    spider = Spider()
    requests = list(spider.probe_jobscz(response, urls=urls))

    assert [request.url for request in requests] == urls
    assert all(request.method == "GET" for request in requests)
    assert all(request.callback == spider.check_jobscz for request in requests)
    assert all(request.errback == spider.check_failure for request in requests)
    assert [request.cb_kwargs for request in requests] == [
        {"urls": [urls[0]]},
        {"urls": [urls[1]]},
    ]
    assert all(request.dont_filter for request in requests)
    assert all(
        request.cookies
        == [
            {
                "name": "beta_bucket",
                "value": "5%3AB",
                "domain": ".jobs.cz",
                "path": "/",
            }
        ]
        for request in requests
    )


def test_spider_probe_jobscz_raises_without_cookie():
    response = TextResponse("https://www.jobs.cz/", status=200)

    with pytest.raises(ValueError):
        list(Spider().probe_jobscz(response, urls=["https://www.jobs.cz/rpd/1/"]))


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.jobs.cz/rpd/2001389794/", True),
        ("https://jobs.cz/rpd/2001389794/", True),
        ("https://abb.jobs.cz/detail-pozice?r=detail&id=2001389794", True),
        ("https://www.notjobs.cz/rpd/2001389794/", False),
        ("https://example.com/?next=https://www.jobs.cz/", False),
    ],
)
def test_is_jobscz_url(url: str, expected: bool):
    assert is_jobscz_url(url) is expected


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


def test_spider_start_probes_jobscz_beta_bucket():
    urls = [
        "https://www.jobs.cz/rpd/2001440830/",
        "https://abb.jobs.cz/detail-pozice?r=detail&id=2001389794",
        "https://example.com/job/",
    ]
    spider = Spider(links=[{"url": url} for url in urls])

    async def collect():
        return [request async for request in spider.start()]

    requests = asyncio.run(collect())

    assert [request.url for request in requests] == [
        "https://example.com/job/",
        "https://www.jobs.cz/",
    ]
    probe = requests[1]
    assert probe.callback == spider.probe_jobscz
    assert probe.errback == spider.check_failure
    assert probe.cb_kwargs == {"urls": urls[:2]}
    assert probe.meta["dont_redirect"] is True
    assert probe.meta["dont_merge_cookies"] is True
    assert probe.meta["handle_httpstatus_list"] == [301, 302]


def test_spider_jobscz_probe_passes_middlewares():
    url = "https://www.jobs.cz/rpd/2001440830/"
    crawler = get_crawler(
        Spider,
        {name: value for name, value in vars(settings).items() if name.isupper()}
        | Spider.custom_settings,
    )
    crawler.spider = Spider(links=[{"url": url}])

    async def collect():
        return [request async for request in crawler.spider.start()]

    probe = asyncio.run(collect())[0]
    response = TextResponse(
        probe.url,
        status=302,
        headers=[
            ("Location", "https://beta.jobs.cz/"),
            ("Set-Cookie", "beta_bucket=5%3AA; path=/; domain=.jobs.cz"),
        ],
        request=probe,
    )

    assert (
        RedirectMiddleware.from_crawler(crawler).process_response(probe, response)
        is response
    )
    HttpErrorMiddleware.from_crawler(crawler).process_spider_input(response)

    requests = list(probe.callback(response, **probe.cb_kwargs))

    assert [request.url for request in requests] == [url]
    assert requests[0].cookies[0]["value"] == "5%3AB"


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
                ("https://acme.jobs.cz/pd/3/", None),
                ("https://beta.jobs.cz/rpd/4/", None),
                ("https://www.jobs.cz/rpd/5/", None),
            ],
            ["Checks of jobs.cz don't work: 5/5 inconclusive"],
            id="subdomains",
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
