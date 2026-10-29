import re
from collections.abc import AsyncGenerator, Generator, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, cast
from urllib.parse import parse_qs, urlparse, urlunparse

from itemloaders.processors import Compose, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import DontCloseSpider
from scrapy.http.response import Response
from scrapy.http.response.html import HtmlResponse
from scrapy.loader import ItemLoader
from twisted.python.failure import Failure

from jg.plucker.items import Job
from jg.plucker.processors import parse_iso_date
from jg.plucker.settings import RETRY_HTTP_CODES


LISTING_URL = "https://www.profesia.sk/praca/informacne-technologie/"

# Listing URL slug of the employment type filter → employment type
EMPLOYMENT_TYPES = {
    "plny-uvazok": "plný úväzok",
    "skrateny-uvazok": "skrátený úväzok",
    "zivnost": "živnosť",
    "na-dohodu-brigady": "na dohodu (brigády)",
    "internship-staz": "stáž",
}

# Value of the remote work filter → whether the job is remote
REMOTE_WORK = {
    "0": False,  # Práca iba na pracovisku
    "1": True,  # Práca iba z domu
    "2": True,  # Možná čiastočne
}

LANGUAGES = ["cs", "en", "sk"]

LOCATION_NOTE_RE = re.compile(r"\s*\((?P<note>[^()]*)\)$")

LOCATION_NOTES = [
    "Pozícia umožňuje občasnú prácu z domu",
    "Pozice umožňuje občasnou práci z domu",
    "Job with occasional home office",
    "Práca vyžaduje cestovanie",
    "The job requires travelling",
]

REMOTE_LOCATIONS = ["Práca z domu", "Remote work"]

WAF_HTTP_CODES = [202, 405]


class UnexpectedMarkupError(Exception):
    pass


class WAFChallengeError(Exception):
    pass


class RequestFailedError(Exception):
    pass


@dataclass
class Card:
    url: str
    title: str
    company_name: str
    company_logo_urls: list[str]
    locations: list[str]
    listing_urls: set[str] = field(default_factory=set)
    employment_types: set[str] = field(default_factory=set)
    remote: bool = False

    def to_dict(self) -> dict[str, Any]:
        """
        Returns the card as a JSON-serializable dict, because the Apify
        request queue can't store anything else in cb_kwargs
        """
        data = asdict(self)
        data["listing_urls"] = sorted(self.listing_urls)
        data["employment_types"] = sorted(self.employment_types)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Card:
        return cls(
            **data
            | {
                "listing_urls": set(data["listing_urls"]),
                "employment_types": set(data["employment_types"]),
            }
        )


class Spider(BaseSpider):
    """
    Crawls listings filtered by employment type and by remote work, so that these
    come from profesia's own data instead of parsing them from the ads. Each ad
    can be in several listings, so the cards get merged first and only then
    the ads get fetched, each exactly once.
    """

    name = "jobs-profesiask"

    custom_settings = {
        "RETRY_TIMES": 10,
        # AWS WAF responds with an empty '202 Accepted' and the 'x-amzn-waf-action: challenge'
        # header when it wants the client to solve a JavaScript challenge, or escalates
        # to a '405 Method Not Allowed' CAPTCHA page
        "RETRY_HTTP_CODES": WAF_HTTP_CODES + RETRY_HTTP_CODES,
        # Otherwise retries would get the cached failed response
        "HTTPCACHE_IGNORE_HTTP_CODES": WAF_HTTP_CODES + RETRY_HTTP_CODES,
    }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._cards: dict[str, Card] = {}

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Spider:
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signal=signals.spider_idle)
        return spider

    async def start(self) -> AsyncGenerator[Request]:
        yield Request(LISTING_URL, callback=self.parse, errback=self.request_failed)

    def request_failed(self, failure: Failure) -> None:
        """
        Fails the run if a request fails even after retries, as a missing
        listing page means missing or incomplete jobs
        """
        raise RequestFailedError(f"{failure.request.url}: {failure.value!r}")

    def parse(self, response: Response) -> Generator[Request]:
        response = cast(HtmlResponse, response)
        raise_for_waf_challenge(response)
        check_filters(response)
        for slug, employment_type in EMPLOYMENT_TYPES.items():
            yield response.follow(
                f"{LISTING_URL}{slug}/",
                callback=self.parse_listing,
                errback=self.request_failed,
                cb_kwargs={"employment_type": employment_type},
            )
        for value, remote in REMOTE_WORK.items():
            if remote:
                yield response.follow(
                    f"{LISTING_URL}?remote_work={value}",
                    callback=self.parse_listing,
                    errback=self.request_failed,
                    cb_kwargs={"remote": True},
                )

    def parse_listing(
        self,
        response: Response,
        employment_type: str | None = None,
        remote: bool = False,
    ) -> Generator[Request]:
        response = cast(HtmlResponse, response)
        raise_for_waf_challenge(response)
        page = get_page(response.url)
        self.logger.debug(f"Parsing listing {response.url} (page: {page})")

        cards = response.xpath("//li[contains(@class, 'list-row')][.//h2/a]")
        for card_el in cards:
            card = parse_card(response, card_el)
            card = self._cards.setdefault(card.url, card)
            card.listing_urls.add(clean_listing_url(response.url))
            if employment_type:
                card.employment_types.add(employment_type)
            card.remote = card.remote or remote
        self.logger.debug(f"Found {len(cards)} job cards on {response.url}")

        next_page_css = ".pagination a.next::attr(href)"
        next_page_link = response.css(next_page_css).get()
        if cards and next_page_link and get_page(next_page_link) == page + 1:
            yield response.follow(
                next_page_link,
                callback=self.parse_listing,
                errback=self.request_failed,
                cb_kwargs={"employment_type": employment_type, "remote": remote},
            )
        else:
            self.logger.debug(f"No next page found for {response.url}")

    def spider_idle(self) -> None:
        if not self._cards:
            return
        cards, self._cards = self._cards, {}
        self.logger.info(f"Listings crawled, fetching {len(cards)} jobs")
        for card in cards.values():
            if not card.employment_types:
                # Not in any employment type listing, but in a remote work one,
                # probably posted while the listings were being crawled
                self.logger.warning(f"No employment types, skipping {card.url}")
                continue
            self.crawler.engine.crawl(
                Request(
                    card.url,
                    callback=self.parse_job,
                    errback=self.request_failed,
                    cb_kwargs={"card": card.to_dict()},
                )
            )
        raise DontCloseSpider

    def parse_job(self, response: Response, card: dict[str, Any]) -> Generator[Job]:
        response = cast(HtmlResponse, response)
        raise_for_waf_challenge(response)
        self.logger.debug(f"Parsing job page {response.url}")
        card = Card.from_dict(card)

        if response.css('#detail .alert a[href*="similar_to="]'):
            # the ad expired after the listings were crawled
            self.logger.info(f"Skipping expired job: {response.url}")
            return

        lang = parse_language(response)
        if lang not in LANGUAGES:
            self.logger.info(f"Skipping job in language {lang!r}: {response.url}")
            return

        loader = Loader(item=Job(), response=response)
        loader.add_value("source", self.name)
        loader.add_value("url", response.url)
        loader.add_value("title", card.title)
        loader.add_value("company_name", parse_company_name(card.company_name))
        loader.add_value("company_logo_urls", card.company_logo_urls)
        loader.add_value(
            "locations_raw", parse_locations(card.locations, remote=card.remote)
        )
        loader.add_value("remote", card.remote)
        loader.add_value("employment_types", sorted(card.employment_types))
        loader.add_value("source_urls", [response.url, *card.listing_urls])

        if not response.css('[itemprop="datePosted"]'):
            raise UnexpectedMarkupError(f"No date posted: {response.url}")
        loader.add_css("posted_on", '[itemprop="datePosted"]::text')

        loader.add_css("company_logo_urls", "img.logo-offer::attr(src)")
        if response.css('[itemprop="description"]'):
            self.logger.debug("Parsing as standard job page")
            loader.add_css("description_html", '[itemprop="description"]')
        elif response.css("#detail .maintextearea"):
            self.logger.debug("Parsing as custom design job page")
            loader.add_css("description_html", "#detail .maintextearea")
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
        else:
            raise UnexpectedMarkupError(f"No description: {response.url}")

        yield loader.load_item()


def raise_for_waf_challenge(response: Response) -> None:
    if response.status in WAF_HTTP_CODES or response.headers.get("x-amzn-waf-action"):
        raise WAFChallengeError(
            f"Blocked by AWS WAF (HTTP {response.status}): {response.url}"
        )


def check_filters(response: HtmlResponse) -> None:
    """
    Raises if the employment type or remote work filters offer other values
    than we know, as then the jobs would get incomplete data
    """
    links = response.css('a[href^="/praca/informacne-technologie/"]')

    employment_types_links = links.css('[data-track-click*="listingLeftMenu_jobtypes"]')
    slugs = {
        urlparse(href).path.strip("/").split("/")[-1]
        for href in employment_types_links.css("::attr(href)").getall()
    }
    if slugs != set(EMPLOYMENT_TYPES):
        raise UnexpectedMarkupError(
            f"Unexpected employment types filter: {sorted(slugs)}"
        )

    remote_work_links = links.css('[data-track-click*="listingLeftMenu_remotework"]')
    values = {
        parse_qs(urlparse(href).query)["remote_work"][0]
        for href in remote_work_links.css("::attr(href)").getall()
    }
    if values != set(REMOTE_WORK):
        raise UnexpectedMarkupError(f"Unexpected remote work filter: {sorted(values)}")


def parse_card(response: HtmlResponse, card_el: Any) -> Card:
    url = clean_url(response.urljoin(card_el.css("h2 a::attr(href)").get()))
    title = card_el.css("h2 .title::text").get()
    company_name = card_el.css(".employer::text").get()
    if not title or not company_name:
        raise UnexpectedMarkupError(f"No title or company name: {url}")
    return Card(
        url=url,
        title=title.strip(),
        company_name=company_name.strip(),
        company_logo_urls=[
            response.urljoin(src)
            for src in card_el.css("img.toplogo::attr(src)").getall()
        ],
        locations=[
            text.strip() for text in card_el.css(".job-location::text").getall()
        ],
    )


def parse_language(response: HtmlResponse) -> str:
    locale = response.css('meta[property="og:locale"]::attr(content)').get()
    if not locale or not (match := re.fullmatch(r"([a-z]{2})_[A-Z]{2}", locale)):
        raise UnexpectedMarkupError(f"Unexpected og:locale {locale!r}: {response.url}")
    return match.group(1)


def get_page(url: str) -> int:
    if page := parse_qs(urlparse(url).query).get("page_num"):
        return int(page[0])
    return 1


def clean_url(url: str) -> str:
    return urlunparse(urlparse(url)._replace(query="", fragment=""))


def clean_listing_url(url: str) -> str:
    parts = urlparse(url)
    query = parse_qs(parts.query)
    query.pop("page_num", None)
    return urlunparse(
        parts._replace(
            query="&".join(f"{key}={values[0]}" for key, values in query.items()),
            fragment="",
        )
    )


def parse_company_name(text: str) -> str:
    """
    Strips a tagline, such as 'CREATIVE sites, s.r.o. | platforma pre ambiciózne e-shopy'
    """
    parts = text.split(" | ")
    if len(parts) > 2:
        raise UnexpectedMarkupError(f"Unexpected company name: {text!r}")
    return parts[0].strip()


def parse_location(text: str) -> str:
    """
    Strips a known note, such as '(Pozícia umožňuje občasnú prácu z domu)'
    """
    text = text.strip()
    if match := LOCATION_NOTE_RE.search(text):
        if match.group("note").strip() not in LOCATION_NOTES:
            raise UnexpectedMarkupError(f"Unexpected location note: {text!r}")
        return text[: match.start()]
    return text


def parse_locations(locations: Iterable[str], remote: bool) -> list[str]:
    """
    Parses locations, dropping placeholders such as 'Práca z domu', which
    are only expected for remote jobs
    """
    parsed = []
    for location in map(parse_location, locations):
        if location in REMOTE_LOCATIONS:
            if not remote:
                raise UnexpectedMarkupError(
                    f"Remote location {location!r}, but the job isn't remote"
                )
        else:
            parsed.append(location)
    return parsed


def is_custom_logo_url(url: str) -> bool:
    filename = urlparse(url).path.split("/")[-1].lower()
    return "logo" in filename and "white" not in filename


def remove_empty(values: Iterable[str]) -> Iterable[str]:
    return filter(None, values)


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    remote_in = MapCompose()
    company_logo_urls_out = Compose(remove_empty, set, sorted)
    employment_types_out = Compose(set, sorted)
    locations_raw_out = Compose(remove_empty, set, sorted)
    posted_on_in = MapCompose(str.strip, parse_iso_date)
    source_urls_out = Compose(set, sorted)
