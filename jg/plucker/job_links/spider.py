from typing import Callable, Generator, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import JobLink
from jg.plucker.settings import HTTPERROR_ALLOWED_CODES


# Trying to be at least somewhat compatible with 'requestListSources'
# See https://docs.apify.com/platform/actors/development/actor-definition/input-schema/specification/v1
class Link(BaseModel):
    url: Url
    method: Literal["GET"] = "GET"


class Params(BaseModel):
    links: list[Link]


class Spider(BaseSpider):
    name = "job-links"

    custom_settings = {
        "HTTPERROR_ALLOWED_CODES": HTTPERROR_ALLOWED_CODES + [404, 410],
    }

    min_items = 0

    domain_mapping = {
        # "linkedin.com": "parse_linkedin",
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
            yield Request(url, callback=callback, meta={"max_retry_times": 10})

    def parse(self, response: TextResponse) -> Generator[JobLink, None, None]:
        url = getattr(response.request, "url", response.url)
        reason = f"HTTP {response.status}"
        if response.status == 200:
            yield JobLink(url=url, ok=True, reason=reason)
        else:
            yield JobLink(url=url, ok=False, reason=reason)
