import json
import re
from typing import Callable, Generator, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse, XmlResponse

from jg.plucker.items import JobCheck
from jg.plucker.url_params import strip_utm_params


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
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "RETRY_TIMES": 10,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "METAREFRESH_ENABLED": False,
    }

    min_items = 0

    domain_mapping = {
        "linkedin.com": "check_linkedin",
        "startupjobs.cz": "check_startupjobs",
    }

    def get_callback(self, url: str) -> Callable:
        netloc = urlparse(url).netloc
        for pattern in self.domain_mapping:
            if pattern in netloc:
                method_name = self.domain_mapping[pattern]
                return getattr(self, method_name)
        return self.check_http

    def start_requests(self) -> Iterable[Request]:
        params = Params.model_validate(self.settings.get("SPIDER_PARAMS"))
        self.logger.info(f"Loaded {len(params.links)} links")

        startupjobs_urls = []
        for url in (str(link.url) for link in params.links):
            netloc = urlparse(url).netloc
            if "linkedin.com" in netloc:
                yield Request(
                    url,
                    callback=self.check_linkedin,
                    meta={"original_url": url},
                )
            elif "startupjobs.cz" in netloc:
                startupjobs_urls.append(url)
            else:
                yield Request(url, callback=self.check_http)

        if startupjobs_urls:
            yield Request(
                "https://feedback.startupjobs.cz/feed/juniorguru.php",
                callback=self.check_startupjobs,
                cb_kwargs={"urls": startupjobs_urls},
            )

    def check_http(self, response: TextResponse) -> JobCheck:
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobCheck(url=response.url, ok=True, reason=reason)
        return JobCheck(url=response.url, ok=False, reason=reason)

    def check_linkedin(self, response: TextResponse) -> JobCheck | Request:
        if response.css(".closed-job").get(None):
            return JobCheck(url=response.url, ok=False, reason="LINKEDIN")
        if response.css(".top-card-layout__cta-container").get(None):
            return JobCheck(url=response.url, ok=True, reason="LINKEDIN")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}")
        return self.check_http(response)

    def check_startupjobs(
        self, response: XmlResponse, urls: list[str]
    ) -> Generator[JobCheck, None, None]:
        current_ids = set(
            parse_startupjobs_id(url)
            for url in response.xpath("//url/text()").extract()
        )
        for url in urls:
            if parse_startupjobs_id(url) in current_ids:
                yield JobCheck(url=url, ok=True, reason="STARTUPJOBS")
            else:
                yield JobCheck(url=url, ok=False, reason="STARTUPJOBS")


def parse_startupjobs_id(url: str) -> int:
    if match := re.search(r"/nabidka/(\d+)/", url):
        return int(match.group(1))
    raise ValueError(f"Could not parse startupjobs ID: {url}")
