from datetime import date
from typing import Any, Generator, Iterable
from urllib.parse import urljoin

from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst
from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.loader import ItemLoader

from juniorguru_plucker.items import Job
from juniorguru_plucker.processors import first, split
from juniorguru_plucker.spiders import JobSpider
from juniorguru_plucker.url_params import strip_params


class Spider(JobSpider):
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
            url = card.css('a[data-link="jd-detail"]::attr(href)').get()
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
            yield response.follow(
                url, callback=self.parse_job, cb_kwargs=dict(item=item)
            )
        urls = [
            response.urljoin(relative_url)
            for relative_url in response.css(".Pagination__link::attr(href)").getall()
            if "page=" in relative_url
        ]
        yield from response.follow_all(urls, callback=self.parse)

    def parse_job(
        self, response: HtmlResponse, item: Job
    ) -> Generator[Job, None, None]:
        loader = Loader(item=item, response=response)
        loader.add_value("url", response.url)
        loader.add_value("source_urls", response.url)
        if "www.jobs.cz" not in response.url:
            yield from self.parse_job_custom(response, loader)
        elif response.css('[class*="--cassiopeia"]').get():
            yield from self.parse_job_standard(response, loader)
        else:
            yield from self.parse_job_company(response, loader)

    def parse_job_standard(
        self, response: HtmlResponse, loader: ItemLoader
    ) -> Generator[Job, None, None]:
        for label in self.employment_types_labels:
            loader.add_xpath(
                "employment_types",
                f"//span[contains(text(), {label!r})]/following-sibling::p/text()",
            )
        loader.add_css("description_html", '[data-jobad="body"]')
        yield loader.load_item()

    def parse_job_company(
        self, response: HtmlResponse, loader: ItemLoader
    ) -> Generator[Job, None, None]:
        for label in self.employment_types_labels:
            loader.add_xpath(
                "employment_types",
                f"//span[contains(text(), {label!r})]/parent::dd/text()",
            )
        loader.add_css("description_html", ".grid__item.e-16 .clearfix")
        loader.add_css("description_html", ".jobad__body")
        loader.add_css("company_logo_urls", ".company-profile__logo__image::attr(src)")
        company_url_relative = response.css(
            ".company-profile__navigation__link::attr(href)"
        ).get()
        loader.add_value("company_url", urljoin(response.url, company_url_relative))
        yield loader.load_item()

    def parse_job_custom(
        self, response: HtmlResponse, loader: ItemLoader
    ) -> Generator[Job, None, None]:
        self.logger.warning("Not implemented yet: custom job portals")
        if False:
            yield


def clean_url(url: str) -> str:
    return strip_params(url, ["positionOfAdInAgentEmail", "searchId", "rps"])


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
