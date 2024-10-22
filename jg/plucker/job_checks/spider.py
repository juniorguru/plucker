import json
from typing import Callable, Iterable, Literal
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_core import Url
from scrapy import Request, Spider as BaseSpider
from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.http import TextResponse

from jg.plucker.items import JobCheck
from jg.plucker.settings import RETRY_HTTP_CODES


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
        "RETRY_HTTP_CODES": RETRY_HTTP_CODES + [403],
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:131.0) Gecko/20100101 Firefox/131.0",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
            "Referer": "https://duckduckgo.com/",
            "Accept-Language": "en-US,en;q=0.8,cs;q=0.6,sk;q=0.4,es;q=0.2",
            "DNT": "1",
        },
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
                cb_kwargs={"url": url},
                meta={"max_retry_times": 10},
            )

    def check_http(self, response: TextResponse, url: str) -> JobCheck:
        reason = f"HTTP {response.status}"
        if response.status == 200:
            return JobCheck(url=url, ok=True, reason=reason)
        return JobCheck(url=url, ok=False, reason=reason)

    def check_linkedin(self, response: TextResponse, url: str) -> JobCheck | Request:
        if "linkedin.com/jobs/view" not in response.url:
            self.logger.warning(f"Unexpected URL: {response.url}")
            if request := response.request:
                if retry_request := get_retry_request(
                    request.replace(url=url, headers={"Host": urlparse(url).netloc}),
                    spider=self,
                    reason=f"Got {response.url}",
                ):
                    return retry_request
                raise RuntimeError(f"Failed to retry {url}")
            raise ValueError("Request object is required to retry")

        if response.css(".closed-job").get(None):
            return JobCheck(url=url, ok=False, reason="LINKEDIN")
        if response.css(".top-card-layout__cta-container").get(None):
            return JobCheck(url=url, ok=True, reason="LINKEDIN")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}")
        return self.check_http(response, url)

    def check_startupjobs(self, response: TextResponse, url: str) -> JobCheck:
        if data_text := response.css("script#__NUXT_DATA__::text").extract_first():
            data = json.loads(data_text)
            status = data[19]

            if status == "published":
                return JobCheck(url=url, ok=True, reason="STARTUPJOBS")
            if status in ["expired", "paused"]:
                return JobCheck(url=url, ok=False, reason="STARTUPJOBS")
            raise NotImplementedError(f"Unexpected status: {status}")

        self.logger.warning(f"Failed to parse {response.url}\n\n{response.text}\n\n")
        return self.check_http(response, url)
