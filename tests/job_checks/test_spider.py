from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, XmlResponse

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


def test_spider_check_startupjobs():
    response = XmlResponse(
        "https://example.com/feed.xml",
        body=Path(FIXTURES_DIR / "startupjobs.xml").read_bytes(),
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
