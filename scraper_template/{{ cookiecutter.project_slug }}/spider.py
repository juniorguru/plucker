from typing import Generator

from scrapy import Request
from scrapy.http import Response, Spider as BaseSpider

from juniorguru_plucker.items import {{ cookiecutter.item_name }}


class Spider(BaseSpider):
    name = "{{ cookiecutter.scraper_name }}"

    start_urls = []

    def parse(self, response: Response) -> Generator[Request | {{ cookiecutter.item_name }}, None, None]:
        raise NotImplementedError()
