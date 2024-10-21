from pathlib import Path
from typing import Callable

import pytest
from scrapy.http import HtmlResponse

from jg.plucker.items import JobLink
from jg.plucker.job_links.spider import Spider


FIXTURES_DIR = Path(__file__).parent


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.jobs.cz/", Spider.parse),
        ("https://www.linkedin.com/", Spider.parse_linkedin),
        ("https://cz.linkedin.com/", Spider.parse_linkedin),
        ("https://www.startupjobs.cz/", Spider.parse_startupjobs),
    ],
)
def test_spider_get_callback(url: str, expected: Callable):
    assert Spider().get_callback(url).__name__ == expected.__name__


@pytest.mark.parametrize(
    "fixture_basename, expected_ok, expected_reason",
    [
        ("linkedin_expired.html", False, "LINKEDIN"),
        ("linkedin_ok.html", True, "LINKEDIN"),
    ],
)
def test_spider_parse_linkedin(
    fixture_basename: str, expected_ok: bool, expected_reason: str
):
    url = "https://cz.linkedin.com/jobs/view/tester-at-coolpeople-4015921370/"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )
    link = next(Spider().parse_linkedin(response, url))

    assert link == JobLink(
        url=url,
        ok=expected_ok,
        reason=expected_reason,
    )


@pytest.mark.parametrize(
    "fixture_basename, expected_ok, expected_reason",
    [
        ("startupjobs_expired.html", False, "STARTUPJOBS"),
        ("startupjobs_ok.html", True, "STARTUPJOBS"),
        ("startupjobs_paused.html", False, "STARTUPJOBS"),
    ],
)
def test_spider_parse_startupjobs(
    fixture_basename: str, expected_ok: bool, expected_reason: str
):
    url = "https://www.startupjobs.cz/nabidka/81775/junior-software-administrator-do-naseho-interniho-it-tymu"
    response = HtmlResponse(
        url, body=Path(FIXTURES_DIR / fixture_basename).read_bytes()
    )
    link = next(Spider().parse_startupjobs(response, url))

    assert link == JobLink(
        url=url,
        ok=expected_ok,
        reason=expected_reason,
    )
