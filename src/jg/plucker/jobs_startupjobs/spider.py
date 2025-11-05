import html
from typing import Generator, cast

from itemloaders.processors import Compose, Identity, MapCompose, TakeFirst
from scrapy import Spider as BaseSpider
from scrapy.http import Response, TextResponse
from scrapy.loader import ItemLoader

from jg.plucker.items import Job
from jg.plucker.processors import parse_iso_date
from jg.plucker.url_params import strip_utm_params


EXPORT_URL = "https://feedback.startupjobs.cz/feed/juniorguru2.php"


class Spider(BaseSpider):
    name = "jobs-startupjobs"

    start_urls = [EXPORT_URL]

    min_items = 1

    def parse(self, response: Response) -> Generator[Job, None, None]:
        response = cast(TextResponse, response)
        for offer in response.json()["offers"]:
            loader = Loader(item=Job(), response=response)
            loader.add_value("source", self.name)
            loader.add_value("source_urls", response.url)
            loader.add_value("title", offer["position"])
            loader.add_value("url", offer["url"])
            loader.add_value("apply_url", offer["url"])
            loader.add_value("company_name", offer["startup"])
            loader.add_value("locations_raw", offer["cities"])
            loader.add_value(
                "remote", "remote" in [t.lower() for t in offer["jobtypes"]]
            )
            loader.add_value("employment_types", offer["jobtypes"])
            loader.add_value("posted_on", offer["lastUpdate"])
            loader.add_value("description_html", offer["description"])
            loader.add_value("company_logo_urls", offer["startupLogo"])
            yield loader.load_item()


def drop_remote(types: list[str]) -> list[str]:
    return [type_ for type_ in types if type_.lower() != "remote"]


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    title_in = MapCompose(html.unescape)
    url_in = MapCompose(str.strip, strip_utm_params)
    company_name_in = MapCompose(html.unescape)
    employment_types_in = Compose(MapCompose(str.strip), drop_remote)
    employment_types_out = Identity()
    posted_on_in = MapCompose(parse_iso_date)
    company_logo_urls_out = Identity()
    remote_in = MapCompose(bool)
    locations_raw_out = Identity()
    source_urls_out = Identity()
