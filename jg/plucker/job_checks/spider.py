import re
from typing import Any, Generator, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse, XmlResponse

from jg.plucker.items import JobCheck
# from jg.plucker.jobs_linkedin.spider import (
#     HEADERS as LINKEDIN_HEADERS,
#     get_job_id as parse_linkedin_id,
# )
from jg.plucker.jobs_startupjobs.spider import EXPORT_URL as STARTUPJOBS_EXPORT_URL
from jg.plucker.scrapers import evaluate_stats


# Trying to be at least somewhat compatible with 'requestListSources'
# See https://docs.apify.com/platform/actors/development/actor-definition/input-schema/specification/v1
class Link(BaseModel):
    url: Url
    method: Literal["GET"] = "GET"


class Params(BaseModel):
    links: list[Link]


class Spider(BaseSpider):
    name = "job-checks"

    custom_settings = {
        "HTTPERROR_ALLOWED_CODES": [404, 410],
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "DOWNLOAD_SLOTS": {"www.linkedin.com": {"concurrency": 1, "delay": 1}},
        "RETRY_TIMES": 10,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "METAREFRESH_ENABLED": False,
    }

    min_items = 0

    @classmethod
    def evaluate_stats(cls, stats: dict[str, Any], min_items: int) -> None:
        max_retries = stats.get("retry/max_reached", 0)
        error_count = stats.get("log_count/ERROR", 0)

        # tolerate up to 3 errors (lost job checks) caused by max retries
        # if error_count and max_retries <= 3:
        # FIXME! see https://github.com/juniorguru/plucker/issues/95
        if error_count and max_retries <= 100:
            stats_copy = stats.copy()
            stats_copy["log_count/ERROR"] = max(0, error_count - max_retries)
            return evaluate_stats(stats_copy, min_items)

        return evaluate_stats(stats, min_items)

    def start_requests(self) -> Iterable[Request]:
        params = Params.model_validate(self.settings.get("SPIDER_PARAMS"))
        self.logger.info(f"Loaded {len(params.links)} links")

        # Sort LinkedIn URLs first as they are usually the slowest
        urls = sorted(
            (str(link.url) for link in params.links),
            key=lambda url: 0 if is_linkedin_url(url) else 1,
        )

        # StartupJobs URLs are checked in bulk
        startupjobs_urls = []

        for url in urls:
            # if is_linkedin_url(url):
            #     yield self._linkedin_request(url)
            # el
            if is_startupjobs_url(url):
                startupjobs_urls.append(url)
            else:
                yield Request(url, callback=self.check_http)

        if startupjobs_urls:
            yield Request(
                STARTUPJOBS_EXPORT_URL,
                callback=self.check_startupjobs,
                cb_kwargs={"urls": startupjobs_urls},
            )

    def check_http(self, response: TextResponse) -> JobCheck:
        self.logger.info(f"Checking {response.url} (HTTP)")
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobCheck(url=response.url, ok=True, reason=reason)
        return JobCheck(url=response.url, ok=False, reason=reason)

    # def _linkedin_request(self, url: str) -> Request:
    #     api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{parse_linkedin_id(url)}"
    #     return Request(
    #         api_url,
    #         headers=LINKEDIN_HEADERS,
    #         callback=self.check_linkedin,
    #         cb_kwargs={"job_url": url},
    #         meta={"impersonate": "chrome124"},
    #     )

    def check_linkedin(
        self, api_response: TextResponse, job_url: str
    ) -> JobCheck | Request:
        self.logger.info(f"Checking {job_url} (LinkedIn)")
        if api_response.status == 404:
            return JobCheck(url=job_url, ok=False, reason="HTTP 404")
        if api_response.css(".closed-job").get(None):
            return JobCheck(url=job_url, ok=False, reason="LINKEDIN")
        if api_response.css(".top-card-layout__cta-container").get(None):
            return JobCheck(url=job_url, ok=True, reason="LINKEDIN")
        self.logger.error(
            f"Failed to parse {api_response.url}, "
            f"status {api_response.status}, "
            f"content length {len(api_response.text)}"
            f"\n\n{api_response.text}"
        )
        raise NotImplementedError("Failed to parse LinkedIn API response")

    def check_startupjobs(
        self, response: XmlResponse, urls: list[str]
    ) -> Generator[JobCheck, None, None]:
        self.logger.info(f"Checking {len(urls)} URLs (StartupJobs)")
        current_ids = set(
            parse_startupjobs_id(url)
            for url in response.xpath("//url/text()").extract()
        )
        for url in urls:
            if parse_startupjobs_id(url) in current_ids:
                yield JobCheck(url=url, ok=True, reason="STARTUPJOBS")
            else:
                yield JobCheck(url=url, ok=False, reason="STARTUPJOBS")


def is_linkedin_url(url: str) -> bool:
    return "linkedin.com" in urlparse(url).netloc


def is_startupjobs_url(url: str) -> bool:
    return "startupjobs.cz" in urlparse(url).netloc


def parse_startupjobs_id(url: str) -> int:
    if match := re.search(r"/nabidka/(\d+)/", url):
        return int(match.group(1))
    raise ValueError(f"Could not parse StartupJobs ID: {url}")
