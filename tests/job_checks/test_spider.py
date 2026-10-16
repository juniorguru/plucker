from pathlib import Path

import pytest
from scrapy.http import TextResponse
from scrapy.http.response.html import HtmlResponse

from jg.plucker.items import JobCheck
from jg.plucker.job_checks.spider import Spider, is_profesiask_url
from jg.plucker.jobs_profesiask.spider import WAFChallengeError
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
    "fixture_basename, expected_ok",
    [
        ("profesiask_expired.html", False),
        ("profesiask_ok.html", True),
        ("profesiask_ok_custom.html", True),
    ],
)
def test_spider_check_profesiask(fixture_basename: str, expected_ok: bool):
    url = "https://www.profesia.sk/praca/softip/O5372508"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )
    link = Spider().check_profesiask(response, job_url=url)

    assert link == JobCheck(url=url, ok=expected_ok, reason="PROFESIASK")


def test_spider_check_profesiask_reports_requested_url():
    job_url = "https://www.profesia.sk/praca/old-slug/O4000000"
    response = HtmlResponse(
        "https://www.profesia.sk/praca/talent-solutions/O4000000",
        body=Path(FIXTURES_DIR / "profesiask_expired.html").read_bytes(),
    )
    link = Spider().check_profesiask(response, job_url=job_url)

    assert link == JobCheck(url=job_url, ok=False, reason="PROFESIASK")


def test_spider_check_profesiask_redirect_to_homepage():
    job_url = "https://www.profesia.sk/praca/softip/O9999999"
    response = HtmlResponse(
        "https://www.profesia.sk/", body=b"<html><body>Homepage</body></html>"
    )
    link = Spider().check_profesiask(response, job_url=job_url)

    assert link == JobCheck(url=job_url, ok=False, reason="PROFESIASK")


def test_spider_check_profesiask_waf_challenge():
    url = "https://www.profesia.sk/praca/softip/O5372508"
    response = HtmlResponse(
        url, status=202, headers={"x-amzn-waf-action": "challenge"}, body=b""
    )

    with pytest.raises(WAFChallengeError):
        Spider().check_profesiask(response, job_url=url)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.profesia.sk/praca/softip/O5372508", True),
        ("https://profesia.sk/praca/softip/O5372508", True),
        ("https://www.jobs.cz/rpd/2000120375/", False),
    ],
)
def test_is_profesiask_url(url: str, expected: bool):
    assert is_profesiask_url(url) is expected


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
        {"log_count/ERROR": 4, "retry/max_reached": 4},
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
