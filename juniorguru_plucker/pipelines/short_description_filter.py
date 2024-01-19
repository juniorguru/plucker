from scrapy import Spider
from scrapy.exceptions import DropItem
from w3lib.html import remove_tags

from juniorguru_plucker.items import Job


class ShortDescription(DropItem):
    pass


class Pipeline:
    min_chars_count = 600

    def process_item(self, job: Job, spider: Spider) -> Job:
        chars_count = len(remove_tags(job["description_html"]))
        if chars_count >= self.min_chars_count:
            return job
        raise ShortDescription(
            f"Description is only {chars_count} characters (limit: {self.min_chars_count})"
        )
