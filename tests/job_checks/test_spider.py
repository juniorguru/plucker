from pathlib import Path

import pytest
from scrapy import Request
from scrapy.http import TextResponse
from scrapy.http.response.html import HtmlResponse
from twisted.internet.error import TimeoutError
from twisted.python.failure import Failure

from jg.plucker.items import JobCheck
from jg.plucker.job_checks.spider import Spider
from jg.plucker.scrapers import StatsError


FIXTURES_DIR = Path(__file__).parent


@pytest.mark.parametrize(
    "fixture_basename, expected_ok, expected_reason",
    [
        ("linkedin_expired.html", False, "LINKEDIN"),
        ("linkedin_ok.html", True, "LINKEDIN"),
    ],
)
def test_spider_check_linkedin(
    fixture_basename: str, expected_ok: bool, expected_reason: str
):
    url = "https://cz.linkedin.com/jobs/view/tester-at-coolpeople-4015921370/"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )
    link = Spider().check_linkedin(response, job_url=url)

    assert link == JobCheck(
        url=url,
        ok=expected_ok,
        reason=expected_reason,
    )


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
    response = TextResponse("https://example.com/redirected/", status=status)
    link = Spider().check_http(response, urls=[url])

    assert link == JobCheck(url=url, ok=expected_ok, reason=f"HTTP {status}")


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


def test_spider_linkedin_request_warns_and_skips(caplog):
    url = "https://www.linkedin.com/jobs/view/tester-at-coolpeople-4015921370/"

    with caplog.at_level("WARNING"):
        request = Spider()._linkedin_request(url)

    assert request is None
    assert f"Skipping {url}, LinkedIn job checks are not supported" in caplog.messages


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
            "spider_exceptions": 0,
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
        {"log_count/ERROR": 1, "spider_exceptions": 1},
    ],
)
def test_evaluate_stats_failing(stats_override: dict):
    with pytest.raises(StatsError):
        Spider.evaluate_stats(
            {
                "item_scraped_count": 10,
                "finish_reason": "finished",
                "item_dropped_reasons_count/MissingRequiredFields": 0,
                "spider_exceptions": 0,
                "log_count/ERROR": 0,
            }
            | stats_override,
            min_items=10,
        )


def test_spider_logs_links_not_assessed(caplog):
    urls = ["https://example.com/job1/", "https://example.com/job2/"]
    spider = Spider(links=[{"url": url} for url in urls])
    spider._expected_urls = set(urls)
    spider.item_scraped(JobCheck(url=urls[0], ok=True, reason="HTTP 200"))

    with caplog.at_level("ERROR"):
        spider.closed("finished")

    assert caplog.messages == [f"Link not assessed: {urls[1]}"]
