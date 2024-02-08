from typing import Generator

from scrapy import Request
from scrapy.http import Response{% if cookiecutter.item_name != "Job" %}, Spider as BaseSpider{% endif %}

from juniorguru_plucker.items import {{ cookiecutter.item_name }}
{% if cookiecutter.item_name == "Job" %}from juniorguru_plucker.spiders import JobSpider{% endif %}


class Spider({% if cookiecutter.item_name == "Job" %}JobSpider{% else %}BaseSpider{% endif %}):
    name = "{{ cookiecutter.scraper_name }}"

    start_urls = []

    def parse(self, response: Response) -> Generator[Request | {{ cookiecutter.item_name }}, None, None]:
        raise NotImplementedError()
