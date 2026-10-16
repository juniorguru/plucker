import re
from typing import Generator, Iterable, cast
from urllib.parse import parse_qs, urlparse, urlunparse

from itemloaders.processors import Compose, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response
from scrapy.http.response.html import HtmlResponse
from scrapy.loader import ItemLoader

from jg.plucker.items import Job
from jg.plucker.processors import parse_iso_date, split
from jg.plucker.settings import RETRY_HTTP_CODES


LOCATION_NOTE_RE = re.compile(r"\s*\((?P<note>[^)]*)\)$")

HYBRID_NOTE_RE = re.compile(r"z domu|z domova|home office|zu hause", re.IGNORECASE)

REMOTE_LOCATIONS = ["práca z domu", "práce z domu", "remote work"]

WAF_HTTP_CODES = [202, 405]

EMPLOYMENT_TYPES_LABELS = [
    "Druh pracovného pomeru",
    "Type of employment",
    "Contract type",
    "Art des Arbeitsverhältnisses",
]


class Spider(BaseSpider):
    name = "jobs-profesiask"

    custom_settings = {
        "RETRY_TIMES": 10,
        # AWS WAF responds with an empty '202 Accepted' and the 'x-amzn-waf-action: challenge'
        # header when it wants the client to solve a JavaScript challenge, or escalates
        # to a '405 Method Not Allowed' CAPTCHA page
        "RETRY_HTTP_CODES": WAF_HTTP_CODES + RETRY_HTTP_CODES,
        "HTTPCACHE_IGNORE_HTTP_CODES": WAF_HTTP_CODES,
    }

    start_urls = [
        "https://www.profesia.sk/praca/informacne-technologie/",
    ]

    def parse(self, response: Response) -> Generator[Request, None, None]:
        response = cast(HtmlResponse, response)
        raise_for_waf_challenge(response)
        page = get_page(response.url)
        self.logger.debug(f"Parsing listing {response.url} (page: {page})")

        card_xpath = "//li[contains(@class, 'list-row')][.//h2/a]"
        cards = list(response.xpath(card_xpath))
        for n, card in enumerate(cards, start=1):
            url = clean_url(
                response.urljoin(cast(str, card.css("h2 a::attr(href)").get()))
            )

            loader = Loader(item=Job(), response=response)
            card_loader = loader.nested_xpath(f"({card_xpath})[{n}]")
            card_loader.add_value("source", self.name)
            card_loader.add_css("title", "h2 .title::text")
            card_loader.add_css("company_name", ".employer::text")
            card_loader.add_css("company_logo_urls", "img.toplogo::attr(src)")
            card_loader.add_css("locations_raw", ".job-location::text")
            card_loader.add_value("source_urls", response.url)
            card_loader.add_value("source_urls", url)
            item = loader.load_item()
            item["remote"] = is_remote(card.css(".job-location::text").getall())
            item["locations_raw"] = remove_remote(item.get("locations_raw", []))

            self.logger.debug(f"Parsing card for {url}")
            yield response.follow(
                url, callback=self.parse_job, cb_kwargs=dict(item=item)
            )
        self.logger.debug(f"Found {len(cards)} job cards on {response.url}")

        next_page_css = ".pagination a.next::attr(href)"
        next_page_link = response.css(next_page_css).get()
        if cards and next_page_link and get_page(next_page_link) == page + 1:
            yield response.follow(next_page_link, callback=self.parse)
        else:
            self.logger.debug(f"No next page found for {response.url}")

    def parse_job(self, response: Response, item: Job) -> Generator[Job, None, None]:
        response = cast(HtmlResponse, response)
        raise_for_waf_challenge(response)
        self.logger.debug(f"Parsing job page {response.url}")

        loader = Loader(item=item, response=response)
        loader.add_value("url", response.url)
        loader.add_value("source_urls", response.url)
        loader.add_css("posted_on", '[itemprop="datePosted"]::text')
        loader.add_css("employment_types", '[itemprop="employmentType"]::text')
        loader.add_css("company_logo_urls", "img.logo-offer::attr(src)")

        if response.css('[itemprop="description"]'):
            self.logger.debug("Parsing as standard job page")
            loader.add_css("description_html", '[itemprop="description"]')
        else:
            self.logger.debug("Parsing as custom design job page")
            loader.add_css("description_html", "#detail .maintextearea")
            loader.add_value(
                "employment_types", parse_custom_employment_types(response)
            )
            loader.add_value(
                "company_logo_urls",
                [
                    response.urljoin(url)
                    for url in response.css(
                        "#detail .maintextearea img::attr(src)"
                    ).getall()
                    if is_custom_logo_url(url)
                ],
            )

        yield loader.load_item()


class WAFChallengeError(Exception):
    pass


def raise_for_waf_challenge(response: Response) -> None:
    if response.status in WAF_HTTP_CODES or response.headers.get("x-amzn-waf-action"):
        raise WAFChallengeError(
            f"Blocked by AWS WAF (HTTP {response.status}): {response.url}"
        )


def get_page(url: str) -> int:
    if page := parse_qs(urlparse(url).query).get("page_num"):
        return int(page[0])
    return 1


def clean_url(url: str) -> str:
    return urlunparse(urlparse(url)._replace(query="", fragment=""))


def parse_custom_employment_types(response: HtmlResponse) -> list[str]:
    # custom designs have various markup, but the label and the value are always next to each other:
    # <strong>Label:</strong> value, <p>Label:</p><p>value</p>, <div>Label</div><span>value</span>
    employment_types = []
    for label_text in EMPLOYMENT_TYPES_LABELS:
        labels = response.xpath(
            f"//*[@id='detail']//*[normalize-space(translate(text(), ':', ''))={label_text!r}]"
        )
        for label in labels:
            value = label.xpath("normalize-space(following-sibling::text()[1])").get()
            if not value:
                value = label.xpath("normalize-space(following-sibling::*[1])").get()
            if value:
                employment_types.append(value)
    return employment_types


def parse_company_name(text: str) -> str:
    return text.split(" | ")[0].strip()


def is_custom_logo_url(url: str) -> bool:
    filename = urlparse(url).path.split("/")[-1].lower()
    return "logo" in filename and "white" not in filename


def parse_location(text: str) -> str:
    return LOCATION_NOTE_RE.sub("", text.strip())


def is_hybrid(location: str) -> bool:
    if match := LOCATION_NOTE_RE.search(location.strip()):
        return bool(HYBRID_NOTE_RE.search(match.group("note")))
    return False


def is_remote(locations: Iterable[str]) -> bool:
    return any(
        parse_location(location).lower() in REMOTE_LOCATIONS or is_hybrid(location)
        for location in locations
    )


def remove_remote(locations: Iterable[str]) -> list[str]:
    return [
        location for location in locations if location.lower() not in REMOTE_LOCATIONS
    ]


def remove_empty(values: Iterable[str]) -> Iterable[str]:
    return filter(None, values)


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    company_name_in = MapCompose(parse_company_name)
    company_logo_urls_out = Compose(remove_empty, set, sorted)
    employment_types_in = MapCompose(str.lower, split)
    employment_types_out = Compose(set, sorted)
    locations_raw_in = MapCompose(parse_location)
    locations_raw_out = Compose(remove_empty, set, sorted)
    posted_on_in = MapCompose(str.strip, parse_iso_date)
    source_urls_out = Compose(set, sorted)
