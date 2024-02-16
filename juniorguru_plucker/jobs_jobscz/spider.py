import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Generator, Iterable, cast
from urllib.parse import urljoin

from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider
from scrapy.http import HtmlResponse, TextResponse
from scrapy.loader import ItemLoader

from juniorguru_plucker.items import Job
from juniorguru_plucker.processors import first, split
from juniorguru_plucker.url_params import get_params, strip_params


WIDGET_DATA_RE = re.compile(r"window\.__LMC_CAREER_WIDGET__\.push\((.+)\);")

WIDGET_DATA_SCRIPT_RE = re.compile(
    r"""
        exports=JSON.parse\('
        (                     # group we're matching
            {"id":
            (                 # one or more characters that are not the start of the word "function"
                (?!function)
                .
            )+
        )
        '\)}
        (,function|]\);)      # either next function or the end of the JSON
    """,
    re.VERBOSE,
)

WIDGET_QUERY_PATH = Path(__file__).parent / "widget.gql"


class Spider(BaseSpider):
    name = "jobs-jobscz"

    start_urls = [
        "https://beta.www.jobs.cz/prace/programator/",
        "https://beta.www.jobs.cz/prace/tester/",
    ]
    employment_types_labels = [
        "Typ pracovního poměru",
        "Employment form",
    ]

    def parse(self, response: HtmlResponse) -> Generator[Request, None, None]:
        card_xpath = "//article[contains(@class, 'SearchResultCard')]"
        for n, card in enumerate(response.xpath(card_xpath), start=1):
            url = cast(str, card.css('a[data-link="jd-detail"]::attr(href)').get())
            track_id = get_track_id(url)

            loader = Loader(item=Job(), response=response)
            card_loader = loader.nested_xpath(f"{card_xpath}[{n}]")
            card_loader.add_value("source", self.name)
            card_loader.add_value("first_seen_on", date.today())
            card_loader.add_css("title", "h2 a::text")
            card_loader.add_css(
                "company_name", ".SearchResultCard__footerItem:nth-child(1) span::text"
            )
            card_loader.add_css("company_logo_urls", ".CompanyLogo img::attr(src)")
            card_loader.add_css(
                "locations_raw", ".SearchResultCard__footerItem:nth-child(2)::text"
            )
            card_loader.add_value("source_urls", response.url)
            card_loader.add_value("source_urls", url)
            item = loader.load_item()

            self.track_logger(track_id).debug(f"Parsing card for {url}")
            yield response.follow(
                url,
                callback=self.parse_job,
                cb_kwargs=dict(item=item, track_id=track_id),
            )
        urls = [
            response.urljoin(relative_url)
            for relative_url in response.css(".Pagination__link::attr(href)").getall()
            if "page=" in relative_url
        ]
        yield from response.follow_all(urls, callback=self.parse)

    def parse_job(
        self, response: HtmlResponse, item: Job, track_id: str
    ) -> Generator[Job | Request, None, None]:
        self.track_logger(track_id).debug("Parsing job page")
        loader = Loader(item=item, response=response)
        loader.add_value("url", response.url)
        loader.add_value("source_urls", response.url)

        if "www.jobs.cz" not in response.url:
            yield from self.parse_job_widget_data(response, item, track_id)
        else:
            self.track_logger(track_id).debug("Parsing as standard job page")
            for label in self.employment_types_labels:
                loader.add_xpath(
                    "employment_types",
                    f"//span[contains(text(), {label!r})]/following-sibling::p/text()",
                )
            loader.add_css("description_html", '[data-jobad="body"]')

            if response.css('[class*="CompanyProfileNavigation"]').get():
                self.track_logger(track_id).debug("Parsing as company job page")
                loader.add_css(
                    "company_logo_urls",
                    ".CompanyProfileNavigation__logo img::attr(src)",
                )
                company_url_relative = response.css(
                    ".CompanyProfileNavigation__menu .Tabs__item:nth-child(2) a::attr(href)"
                ).get()
                loader.add_value(
                    "company_url", urljoin(response.url, company_url_relative)
                )

            yield loader.load_item()

    def parse_job_widget_data(
        self, response: HtmlResponse, item: Job, track_id: str
    ) -> Generator[Request, None, None]:
        try:
            self.track_logger(track_id).debug("Looking for widget data in the HTML")
            widget_data = json.loads(response.css("script::text").re(WIDGET_DATA_RE)[0])
        except IndexError:
            self.track_logger(track_id).debug(
                "Looking for widget data in attached JavaScript"
            )
            script_url = response.css(
                'script[src*="assets/js/script.min.js"]::attr(src)'
            ).get()
            yield response.follow(
                script_url,
                callback=self.parse_job_widget_script,
                cb_kwargs=dict(item=item, html_response=response, track_id=track_id),
            )
        else:
            yield from self.parse_job_widget(
                response,
                item,
                widget_host=widget_data["host"],
                widget_api_key=widget_data["apiKey"],
                widget_id=widget_data["widgetId"],
                track_id=track_id,
            )

    def parse_job_widget_script(
        self,
        script_response: TextResponse,
        html_response: HtmlResponse,
        item: Job,
        track_id: str,
    ) -> Generator[Request, None, None]:
        if match := re.search(WIDGET_DATA_SCRIPT_RE, script_response.text):
            data_text = re.sub(r"\'", r"\\'", match.group(1))
            data = json.loads(data_text)

            widget_name = select_widget(list(data["widgets"].keys()))
            widget_data = data["widgets"][widget_name]

            yield from self.parse_job_widget(
                html_response,
                item,
                widget_host=data["host"],
                widget_api_key=widget_data["apiKey"],
                widget_id=widget_data["id"],
                track_id=track_id,
            )
        else:
            raise NotImplementedError("Widget data not found")

    def parse_job_widget(
        self,
        response: HtmlResponse,
        item: Job,
        widget_host: str,
        widget_api_key: str,
        widget_id: str,
        track_id: str,
    ) -> Generator[Request, None, None]:
        loader = Loader(item=item, response=response)
        loader.add_value("url", response.url)
        loader.add_value("company_url", f"https://{widget_host}")
        loader.add_value("source_urls", response.url)

        self.track_logger(track_id).debug("Requesting data from job widget API")
        params = get_params(response.url)
        yield Request(
            "https://api.capybara.lmc.cz/api/graphql/widget",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": widget_api_key,
            },
            body=json.dumps(
                dict(
                    operationName="DETAIL_QUERY",
                    variables=dict(
                        jobAdId=params["id"],
                        gaId=None,
                        lmcVisitorId=None,
                        rps=int(params["rps"]),
                        impressionId=params["impressionId"],
                        cookieConsent=[],
                        matejId="",
                        jobsUserId="",
                        timeId=str(uuid.uuid4()),
                        widgetId=widget_id,
                        host=widget_host,
                        referer=response.url,
                        version="v3.49.1",
                        pageReferer="https://beta.www.jobs.cz/",
                    ),
                    query=load_gql(WIDGET_QUERY_PATH),
                )
            ),
            callback=self.parse_job_widget_api,
            cb_kwargs=dict(item=loader.load_item(), track_id=track_id),
        )

    def parse_job_widget_api(
        self, response: TextResponse, item: Job, track_id: str
    ) -> Generator[Job, None, None]:
        self.track_logger(track_id).debug("Parsing job widget API response")
        payload = cast(dict, response.json())
        job_ad = payload["data"]["widget"]["jobAd"]

        loader = Loader(item=item, response=response)
        loader.add_value("description_html", job_ad["content"]["htmlContent"])

        first_seen_on = datetime.fromisoformat(job_ad["validFrom"]).date()
        loader.add_value("first_seen_on", first_seen_on)

        for location in job_ad["locations"]:
            location_parts = [location["city"], location["region"], location["country"]]
            location_parts = filter(None, location_parts)
            loader.add_value("locations_raw", ", ".join(location_parts))

        for employment_type in job_ad["parameters"]["employmentTypes"]:
            loader.add_value("employment_types", employment_type)

        yield loader.load_item()

    def track_logger(self, track_id: str) -> logging.LoggerAdapter:
        logger = logging.getLogger(f"{self.name}.{track_id}")
        return logging.LoggerAdapter(logger, {"spider": self, "track_id": track_id})


@lru_cache
def get_track_id(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:10]


@lru_cache
def load_gql(path: str | Path) -> str:
    return Path(path).read_text()


def select_widget(names: list[str]) -> str:
    for name in names:
        if name.startswith("main"):
            return name
    return names[0]


def clean_url(url: str) -> str:
    return strip_params(
        url, ["positionOfAdInAgentEmail", "searchId", "rps", "impressionId"]
    )


def join(values: Iterable[str]) -> str:
    return "".join(values)


def remove_empty(values: Iterable[Any]) -> Iterable[Any]:
    return filter(None, values)


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    url_in = Compose(first, clean_url)
    company_url_in = Compose(first, clean_url)
    company_logo_urls_in = Identity()
    company_logo_urls_out = Compose(set, list)
    description_html_out = Compose(join)
    employment_types_in = MapCompose(str.lower, split)
    employment_types_out = Identity()
    locations_raw_out = Compose(remove_empty, set, list)
    source_urls_out = Compose(set, list)
    first_seen_on_in = Identity()
    first_seen_on_out = min
