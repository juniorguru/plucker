from typing import Generator

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import {{ cookiecutter.item_name }}


class Spider(BaseSpider):
    name = "{{ cookiecutter.scraper_name }}"

    start_urls = []

    def parse(self, response: Response) -> Generator[Request | {{ cookiecutter.item_name }}, None, None]:
        raise NotImplementedError()
