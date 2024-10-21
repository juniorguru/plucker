import json
from typing import Callable, Generator, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.http import TextResponse

from jg.plucker.items import JobLink
from jg.plucker.settings import RETRY_HTTP_CODES


# Trying to be at least somewhat compatible with 'requestListSources'
# See https://docs.apify.com/platform/actors/development/actor-definition/input-schema/specification/v1
class Link(BaseModel):
    url: Url
    method: Literal["GET"] = "GET"


class Params(BaseModel):
    links: list[Link]


class Spider(BaseSpider):
    name = "job-links"

    download_delay = 4

    custom_settings = {
        "HTTPERROR_ALLOWED_CODES": [404, 410],
        "RETRY_HTTP_CODES": RETRY_HTTP_CODES + [403],
    }

    min_items = 0

    domain_mapping = {
        "linkedin.com": "parse_linkedin",
        "startupjobs.cz": "parse_startupjobs",
    }

    def get_callback(self, url: str) -> Callable:
        netloc = urlparse(url).netloc
        for pattern in self.domain_mapping:
            if pattern in netloc:
                method_name = self.domain_mapping[pattern]
                return getattr(self, method_name)
        return self.parse

    def start_requests(self) -> Iterable[Request]:
        params = Params.model_validate(self.settings.get("SPIDER_PARAMS"))
        self.logger.info(f"Loaded {len(params.links)} links")
        for url in (str(link.url) for link in params.links):
            callback = self.get_callback(url)
            self.logger.info(f"Processing {url} with {callback.__name__}()")
            yield Request(
                url,
                callback=callback,
                cb_kwargs={"url": url},
                meta={"max_retry_times": 10},
            )

    def parse(self, response: TextResponse, url: str) -> JobLink:
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobLink(url=url, ok=True, reason=reason)
        return JobLink(url=url, ok=False, reason=reason)

    def parse_linkedin(self, response: TextResponse, url: str) -> JobLink | Request:
        if "linkedin.com/jobs/view" not in response.url:
            if not response.request:
                raise ValueError("Request object is required to retry")
            if request := get_retry_request(
                response.request.replace(url=url),
                spider=self,
                reason=f"Got {response.url}",
            ):
                return request
            self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}")
            return self.parse(response, url)

        if response.css(".closed-job").get(None):
            return JobLink(url=url, ok=False, reason="LINKEDIN")
        if response.css(".top-card-layout__cta-container").get(None):
            return JobLink(url=url, ok=True, reason="LINKEDIN")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}")
        return self.parse(response, url)

    def parse_startupjobs(self, response: TextResponse, url: str) -> JobLink:
        if data_text := response.css("script#__NUXT_DATA__::text").extract_first():
            data = json.loads(data_text)
            status = data[19]

            if status == "published":
                return JobLink(url=url, ok=True, reason="STARTUPJOBS")
            if status in ["expired", "paused"]:
                return JobLink(url=url, ok=False, reason="STARTUPJOBS")
            raise NotImplementedError(f"Unexpected status: {status}")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}\n\n")
        return self.parse(response, url)
