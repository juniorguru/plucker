import re
from typing import Any, AsyncGenerator, Generator
from urllib.parse import urlparse

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import JobCheck
from jg.plucker.jobs_startupjobs.spider import EXPORT_URL as STARTUPJOBS_EXPORT_URL
from jg.plucker.scrapers import Link, evaluate_stats, parse_links


class Spider(BaseSpider):
    name = "job-checks"

    custom_settings = {
        "HTTPCACHE_ENABLED": False,
        "HTTPERROR_ALLOWED_CODES": [404, 410],
        "RETRY_TIMES": 10,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "METAREFRESH_ENABLED": False,
    }

    min_items = 0

    @classmethod
    def evaluate_stats(cls, stats: dict[str, Any], min_items: int) -> None:
        # TODO is this still needed?
        max_retries = stats.get("retry/max_reached", 0)
        error_count = stats.get("log_count/ERROR", 0)

        if error_count and max_retries <= 3:
            stats_copy = stats.copy()
            stats_copy["log_count/ERROR"] = max(0, error_count - max_retries)
            return evaluate_stats(stats_copy, min_items)

        return evaluate_stats(stats, min_items)

    def __init__(self, name: str | None = None, links: list[Link] | None = None):
        super().__init__(name)
        self._start_urls = parse_links(links)

    async def start(self) -> AsyncGenerator[Request, None]:
        if not self._start_urls:
            raise ValueError("No links provided")
        self.logger.info(f"Loading {len(self._start_urls)} links")
        startupjobs_urls = []  # StartupJobs URLs bulk
        for url in self._start_urls:
            if is_linkedin_url(url):
                yield self._linkedin_request(url)
            elif is_startupjobs_url(url):
                startupjobs_urls.append(url)
            else:
                yield Request(url, method="HEAD", callback=self.check_http)
        if startupjobs_urls:
            yield Request(
                STARTUPJOBS_EXPORT_URL,
                callback=self.check_startupjobs,
                cb_kwargs={"urls": startupjobs_urls},
            )

    def check_http(self, response: Response) -> JobCheck:
        self.logger.info(f"Checking {response.url} (HTTP)")
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobCheck(url=response.url, ok=True, reason=reason)
        return JobCheck(url=response.url, ok=False, reason=reason)

    def _linkedin_request(self, url: str) -> Request:
        raise NotImplementedError("LinkedIn not supported")

    def check_linkedin(
        self, api_response: Response, job_url: str
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
        self, response: Response, urls: list[str]
    ) -> Generator[JobCheck, None, None]:
        self.logger.info(f"Checking {len(urls)} URLs (StartupJobs)")
        data = response.json()
        current_ids = set(
            parse_startupjobs_id(offer["url"]) for offer in data.get("offers", [])
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
