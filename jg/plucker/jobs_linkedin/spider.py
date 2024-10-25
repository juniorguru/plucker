import re
from typing import Callable, Generator
from urllib.parse import urlencode, urlparse

from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider
from scrapy.http import HtmlResponse
from scrapy.loader import ItemLoader

from jg.plucker.items import Job
from jg.plucker.processors import first, last, parse_relative_date, split
from jg.plucker.url_params import (
    get_param,
    increment_param,
    replace_in_params,
    strip_params,
    strip_utm_params,
)


HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
    "Host": "www.linkedin.com",
    "Referer": (
        "https://www.linkedin.com/jobs/search"
        "?original_referer=https%3A%2F%2Fwww.linkedin.com%2F"
        "&currentJobId=3864058898"
        "&position=2"
        "&pageNum=0"
    ),
    "Accept-Language": "en-us",
    "DNT": "1",
}

SEARCH_BASE_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

JOB_BASE_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"


class Spider(BaseSpider):
    name = "jobs-linkedin"

    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "RETRY_TIMES": 10,
        "DOWNLOAD_DELAY": 1.5,
        "DEFAULT_REQUEST_HEADERS": HEADERS,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "METAREFRESH_ENABLED": False,
    }

    search_params = {
        "f_TPR": "r2592000",  # past month
    }

    search_terms = [
        "junior software engineer",
        "junior developer",
        "junior vyvojar",
        "junior programator",
        "junior tester",
        "junior data",
    ]

    locations = ["Czechia", "Slovakia"]

    lang_cookies = {"lang": "v=2&lang=en-us"}

    results_per_request = 25

    def start_requests(self) -> Generator[Request, None, None]:
        for location in self.locations:
            for search_term in self.search_terms:
                self.logger.info(f"Starting with {search_term!r} ({location})")
                params = dict(
                    keywords=search_term,
                    location=location,
                    **self.search_params,
                )
                url = f"{SEARCH_BASE_URL}?{urlencode(params)}"
                yield self._request(url, self.parse_search)

    def parse_search(self, response: HtmlResponse) -> Generator[Request, None, None]:
        urls = [
            f"{JOB_BASE_URL}/{get_job_id(url)}"
            for url in response.css(
                'a[href*="linkedin.com/jobs/view/"]::attr(href)'
            ).getall()
        ]
        self.logger.info(f"Found {len(urls)} job URLs: {response.url}")
        for url in urls:
            yield self._request(
                url, self.parse_job, cb_kwargs={"source_url": response.url}
            )

        if len(urls) >= self.results_per_request:
            url = increment_param(response.url, "start", self.results_per_request)
            self.logger.info(f"Paginating: {url}")
            yield self._request(url, self.parse_search)

    def parse_job(
        self, response: HtmlResponse, source_url: str
    ) -> Generator[Job | Request, None, None]:
        loader = Loader(item=Job(), response=response)
        loader.add_value("source", self.name)
        loader.add_value("source_urls", source_url)
        loader.add_value("source_urls", response.url)
        loader.add_css("title", "h2::text")
        loader.add_css("remote", "h2::text")
        loader.add_css("url", ".top-card-layout__entity-info > a::attr(href)")
        loader.add_css("apply_url", ".apply-button::attr(href)")
        loader.add_css("company_name", ".topcard__org-name-link::text")
        loader.add_css(
            "company_name", ".top-card-layout .topcard__flavor:nth-child(1)::text"
        )
        loader.add_css(
            "locations_raw", ".top-card-layout .topcard__flavor:nth-child(2)::text"
        )
        loader.add_xpath(
            "employment_types",
            "//h3[contains(., 'Employment type')]/following-sibling::span/text()",
        )
        loader.add_css("posted_on", ".posted-time-ago__text::text")
        loader.add_css("description_html", ".description__text")
        loader.add_css(
            "company_logo_urls",
            'img.artdeco-entity-image[src*="company-logo"]::attr(src)',
        )
        loader.add_css(
            "company_logo_urls",
            'img.artdeco-entity-image[data-delayed-url*="company-logo"]::attr(data-delayed-url)',
        )
        item = loader.load_item()

        if item.get("apply_url"):
            yield response.follow(
                item["apply_url"],
                callback=self.verify_job,
                cb_kwargs=dict(item=item),
            )
        else:
            yield item

    def verify_job(
        self, response: HtmlResponse, item: Job
    ) -> Generator[Job, None, None]:
        """
        Verify apply URL

        Filters out URLs to broken external URLs and cuts redirects, if any.
        """
        loader = Loader(item=item)
        loader.add_value("source_urls", response.url)
        loader.replace_value("apply_url", response.url)
        yield loader.load_item()

    def _request(
        self, url: str, callback: Callable, cb_kwargs: dict | None = None
    ) -> Request:
        return Request(
            url,
            cookies=self.lang_cookies,
            callback=callback,
            cb_kwargs=cb_kwargs or {},
            meta={"impersonate": "edge101"},
        )


def get_job_id(url: str) -> str:
    if match := re.search(r"-(\d+)$", urlparse(url).path):
        return match.group(1)
    raise ValueError(f"Could not parse LinkedIn job ID: {url}")


def clean_proxied_url(url: str) -> str:
    proxied_url = get_param(url, "url")
    if proxied_url:
        proxied_url = strip_utm_params(proxied_url)
        return replace_in_params(
            proxied_url, "linkedin", "juniorguru", case_insensitive=True
        )
    return url


def clean_validated_url(url: str) -> str:
    if url and "validate.perfdrive.com" in url:
        if ssc_url := get_param(url, "ssc"):
            return ssc_url
        raise ValueError(f"Could not parse SSC URL: {url}")
    return url


def clean_url(url: str) -> str:
    if url and "linkedin.com" in url:
        return strip_params(url, ["refId", "trk", "trackingId"])
    if url and "talentify.io" in url:
        return strip_params(url, ["tdd"])
    if url and "neuvoo.cz" in url:
        return strip_params(url, ["puid"])
    if url and "lever.co" in url:
        return re.sub(r"/apply$", "/", url)
    url = strip_utm_params(url)
    url = replace_in_params(url, "linkedin", "juniorguru", case_insensitive=True)
    return url


def parse_remote(text: str) -> bool:
    return bool(re.search(r"\bremote(ly)?\b", text, re.IGNORECASE))


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    url_in = Compose(first, clean_url)
    apply_url_in = Compose(last, clean_proxied_url, clean_validated_url, clean_url)
    company_url_in = Compose(first, clean_url)
    employment_types_in = MapCompose(str.lower, split)
    employment_types_out = Identity()
    posted_on_in = Compose(first, parse_relative_date)
    company_logo_urls_out = Compose(set, list)
    remote_in = MapCompose(parse_remote)
    locations_raw_out = Identity()
    source_urls_out = Identity()
