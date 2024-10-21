import json
from typing import Callable, Generator, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse
from scrapy.downloadermiddlewares.retry import get_retry_request

from jg.plucker.items import JobLink


# Trying to be at least somewhat compatible with 'requestListSources'
# See https://docs.apify.com/platform/actors/development/actor-definition/input-schema/specification/v1
class Link(BaseModel):
    url: Url
    method: Literal["GET"] = "GET"


class Params(BaseModel):
    links: list[Link]


class Spider(BaseSpider):
    name = "job-links"

    download_delay = 1

    custom_settings = {"HTTPERROR_ALLOWED_CODES": [404, 410]}

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
                meta={"max_retry_times": 5},
            )

    def parse(self, response: TextResponse, url: str) -> Generator[JobLink, None, None]:
        reason = f"HTTP {response.status}"
        if response.status == 200:
            yield JobLink(url=url, ok=True, reason=reason)
        else:
            yield JobLink(url=url, ok=False, reason=reason)

    def parse_linkedin(
        self, response: TextResponse, url: str
    ) -> Generator[JobLink | Request, None, None]:
        if "linkedin.com/jobs/view" not in response.url:
            if not response.request:
                raise ValueError("Request object is required to retry")
            if request := get_retry_request(
                response.request, spider=self, reason=f"Got {response.url}"
            ):
                yield request
            else:
                self.logger.warning(
                    f"Failed to parse {response.url}\n\n{response.text}\n\n"
                )
                yield from self.parse(response, url)
        else:
            if response.css(".closed-job").get(None):
                yield JobLink(url=url, ok=False, reason="LINKEDIN")
            elif response.css(".top-card-layout__cta-container").get(None):
                yield JobLink(url=url, ok=True, reason="LINKEDIN")
            else:
                self.logger.warning(
                    f"Failed to parse {response.url}\n\n{response.text}\n\n"
                )
                yield from self.parse(response, url)

    def parse_startupjobs(
        self, response: TextResponse, url: str
    ) -> Generator[JobLink, None, None]:
        if data_text := response.css("script#__NUXT_DATA__::text").extract_first():
            data = json.loads(data_text)
            status = data[19]
            if status == "published":
                yield JobLink(url=url, ok=True, reason="STARTUPJOBS")
            elif status in ["expired", "paused"]:
                yield JobLink(url=url, ok=False, reason="STARTUPJOBS")
            else:
                raise NotImplementedError(f"Unexpected status: {status}")
        else:
            self.logger.warning(
                f"Failed to parse {response.url}\n\n{response.text}\n\n"
            )
            yield from self.parse(response, url)
