import html
import re
from collections.abc import Generator
from typing import cast

from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider
from scrapy.http import Response, TextResponse
from scrapy.loader import ItemLoader

from jg.plucker.items import Job
from jg.plucker.processors import parse_iso_date


EXPORT_URL = "https://feedback.startupjobs.cz/feed/juniorguru2.php"

LOGO_URL_RE = re.compile(r"https://assets\.startupjobs\.cz/LOGO/\d+/[0-9a-f]+\.\w+")


class Spider(BaseSpider):
    name = "jobs-startupjobs"

    start_urls = [EXPORT_URL]

    min_items = 1

    def parse(self, response: Response) -> Generator[Job | Request]:
        response = cast(TextResponse, response)
        offers_by_startup: dict[str, list[dict]] = {}
        for offer in response.json()["offers"]:
            if is_invalid(offer):
                self.logger.warning(f"Skipping invalid offer: {offer.get('url')!r}")
                continue
            if startup_url := offer.get("startupURL"):
                offers_by_startup.setdefault(startup_url, []).append(offer)
            else:
                self.logger.warning(f"Offer without startup URL: {offer['url']!r}")
                yield load_job(offer, self.name, response.url)

        # The logo URLs in the feed are broken, the working ones are only
        # on the startup pages, see https://github.com/juniorguru/plucker/issues/200
        for startup_url, offers in offers_by_startup.items():
            yield Request(
                startup_url,
                callback=self.parse_startup,
                errback=self.handle_startup_error,
                cb_kwargs={"offers": offers, "feed_url": response.url},
            )

    def parse_startup(
        self, response: Response, offers: list[dict], feed_url: str
    ) -> Generator[Job]:
        response = cast(TextResponse, response)
        logo_urls = set(LOGO_URL_RE.findall(response.text))
        for offer in offers:
            logo_url = select_logo_url(logo_urls, offer.get("startupLogo"))
            if not logo_url:
                self.logger.warning(
                    f"No logo found for {offer['url']!r} on {response.url}"
                )
            yield load_job(offer, self.name, feed_url, logo_url)

    def handle_startup_error(self, failure) -> Generator[Job]:
        request = failure.request
        self.logger.warning(f"Failed to fetch {request.url}: {failure.value!r}")
        for offer in request.cb_kwargs["offers"]:
            yield load_job(offer, self.name, request.cb_kwargs["feed_url"])


def load_job(
    offer: dict, source: str, feed_url: str, logo_url: str | None = None
) -> Job:
    loader = Loader(item=Job())
    loader.add_value("source", source)
    loader.add_value("source_urls", feed_url)
    loader.add_value("title", offer["position"])
    loader.add_value("url", offer["url"])
    loader.add_value("company_name", offer["startup"])
    loader.add_value("locations_raw", offer["cities"])
    loader.add_value("remote", "remote" in [t.lower() for t in offer["jobtypes"]])
    loader.add_value("employment_types", offer["jobtypes"])
    loader.add_value("posted_on", offer["lastUpdate"])
    loader.add_value("description_html", offer["description"])
    loader.add_value("company_logo_urls", logo_url)
    return loader.load_item()


def select_logo_url(logo_urls: set[str], feed_logo_url: str | None) -> str | None:
    if not feed_logo_url:
        return None
    file_name = feed_logo_url.rstrip("/").split("/")[-1]
    for logo_url in sorted(logo_urls):
        if logo_url.split("/")[-1] == file_name:
            return logo_url
    return None


def is_invalid(offer: dict) -> bool:
    return (
        not (offer.get("position") or "").strip()
        or not (offer.get("description") or "").strip()
    )


def drop_remote(types: list[str]) -> list[str]:
    return [type_ for type_ in types if type_.lower() != "remote"]


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    title_in = MapCompose(html.unescape)
    company_name_in = MapCompose(html.unescape)
    employment_types_in = Compose(MapCompose(str.strip), drop_remote)
    employment_types_out = Identity()
    posted_on_in = MapCompose(parse_iso_date)
    company_logo_urls_out = Identity()
    remote_in = MapCompose(bool)
    locations_raw_out = Identity()
    source_urls_out = Identity()
