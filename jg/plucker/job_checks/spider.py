import json
from typing import Callable, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import JobCheck
from jg.plucker.settings import RETRY_HTTP_CODES as DEFAULT_RETRY_HTTP_CODES


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
        "RETRY_HTTP_CODES": DEFAULT_RETRY_HTTP_CODES + [403],
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
        for url in (str(link.url) for link in params.links):
            callback = self.get_callback(url)
            self.logger.debug(f"Processing {url} with {callback.__name__}()")
            yield Request(
                url,
                callback=callback,
                meta={"original_url": url},
            )

    def check_http(self, response: TextResponse) -> JobCheck:
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobCheck(url=response.url, ok=True, reason=reason)
        return JobCheck(url=response.url, ok=False, reason=reason)

    def check_linkedin(self, response: TextResponse) -> JobCheck | Request:
        self.logger.info(f"Checking LinkedIn: {self.get_info(response)}")
        if response.css(".closed-job").get(None):
            return JobCheck(url=response.url, ok=False, reason="LINKEDIN")
        if response.css(".top-card-layout__cta-container").get(None):
            return JobCheck(url=response.url, ok=True, reason="LINKEDIN")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}")
        return self.check_http(response)

    def check_startupjobs(self, response: TextResponse) -> JobCheck:
        self.logger.info(f"Checking StartupJobs: {self.get_info(response)}")
        if data_text := response.css("script#__NUXT_DATA__::text").extract_first():
            data = json.loads(data_text)
            status = data[19]

            if status == "published":
                return JobCheck(url=response.url, ok=True, reason="STARTUPJOBS")
            if status in ["expired", "paused"]:
                return JobCheck(url=response.url, ok=False, reason="STARTUPJOBS")
            raise NotImplementedError(f"Unexpected status: {status}")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}\n\n")
        return self.check_http(response)

    def get_info(self, response: TextResponse) -> dict:
        return {
            "request_url": getattr(response.request, "url", None),
            "request_headers": getattr(response.request, "headers", None),
            "request_proxy": getattr(response.request, "meta", {}).get("proxy"),
            "response_url": response.url,
            "response_status": response.status,
        }
