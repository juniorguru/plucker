from scrapy import Spider
from scrapy.exceptions import DropItem

from juniorguru_plucker.items import Job


class BrokenEncoding(DropItem):
    pass


class Pipeline:
    MAX_QM_COUNT = 20

    def process_item(self, job: Job, spider: Spider) -> Job:
        qm_count = job["description_html"].count("?")
        if qm_count <= self.MAX_QM_COUNT:
            return job
        raise BrokenEncoding(
            f"Found {qm_count} question marks (limit: {self.MAX_QM_COUNT})"
        )
