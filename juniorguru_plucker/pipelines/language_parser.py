import langdetect
from scrapy import Spider
from w3lib.html import remove_tags

from juniorguru_plucker.items import Job


class Pipeline:
    def process_item(self, job: Job, spider: Spider):
        job["lang"] = parse_language(job["description_html"])
        return job


def parse_language(description_html: str) -> str:
    return langdetect.detect(remove_tags(description_html))
