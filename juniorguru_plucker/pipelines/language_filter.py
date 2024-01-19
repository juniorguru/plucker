from scrapy import Spider
from scrapy.exceptions import DropItem

from juniorguru_plucker.items import Job


class IrrelevantLanguage(DropItem):
    pass


class Pipeline:
    RELEVANT_LANGS = ["cs", "en"]

    def process_item(self, job: Job, spider: Spider) -> Job:
        if job["lang"] not in self.RELEVANT_LANGS:
            raise IrrelevantLanguage(
                f"Language detected as '{job['lang']}' (relevant: {', '.join(self.RELEVANT_LANGS)})"
            )
        return job
