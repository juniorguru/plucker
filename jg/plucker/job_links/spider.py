from typing import Callable, Generator, Iterable
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import JobLink
from jg.plucker.settings import HTTPERROR_ALLOWED_CODES


class Params(BaseModel):
    urls: list[Url]


class Spider(BaseSpider):
    name = "job-links"

    custom_settings = {
        "HTTPERROR_ALLOWED_CODES": HTTPERROR_ALLOWED_CODES + [404, 410],
    }

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
        for url in map(str, params.urls):
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
