from datetime import date
from typing import Generator, cast

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response
from scrapy.http.response.text import TextResponse

from jg.plucker.items import Job


class Spider(BaseSpider):
    name = "jobs-govcz"

    category_id = "128"  # Informační a komunikační technologie

    start_urls = [
        "https://portal.isoss.gov.cz/irj/portal/anonymous/mvrest?path=/eosm-public-offer&officeLabels=%7B%7D&page=1&pageSize=100000&sortColumn=zdatzvsm&sortOrder=-1"
    ]

    def parse(self, response: Response) -> Generator[Request | Job, None, None]:
        response = cast(TextResponse, response)
        jobs = response.json()
        self.logger.info(f"Fetched {len(jobs)} jobs")
        jobs = [job for job in jobs if self.is_tech_job(job)]
        self.logger.info(f"Found {len(jobs)} tech jobs")

        for job in jobs:
            title = job["structIsZdata"]["zslmsuSt"]
            self.logger.debug(f"Scraping: {title}")
            yield Job(
                title=title[0].upper() + title[1:],
                posted_on=date.fromisoformat(job["structIsZdata"]["zdatzvsm"][:10]),
                url=(
                    "https://portal.isoss.gov.cz/irj/portal/anonymous/eosmlistpublic"
                    f"#/detail/{job['structIsZdata']['zslmsuId']}"
                ),
                company_name=job["structIsZdata"]["zsuosmSt"],
                company_logo_urls=[
                    "https://digitalnicesko.gov.cz/media/cache/b8/9e/b89e8e2d9063599378be731316c74393/statni-sprava-podklady-pro-media-16ku9-02.webp"
                ],
                locations_raw=[job["structIsZdata"]["zspobcTx"]],
                description_html=job["tableItPopci"][0]["zslmsuCi"],
                source=self.name,
                source_urls=[response.url],
            )

    def is_tech_job(self, job: dict) -> bool:
        for category in job["tableItObslu"]:
            if category["zobsluSh"] == self.category_id:
                return True
        return False


# [{"type":"110","abbrev":"REF","text":"referent"},{"type":"111","abbrev":"ORF","text":"odborný referent"},{"type":"112","abbrev":"VRF","text":"vrchní referent"},{"type":"121","abbrev":"RAD","text":"rada"},{"type":"131","abbrev":"ORA","text":"odborný rada"},{"type":"132","abbrev":"MRA","text":"ministerský rada"},{"type":"133","abbrev":"VLR","text":"vládní rada"},{"type":"141","abbrev":"VRR","text":"vrchní rada"},{"type":"142","abbrev":"VMR","text":"vrchní ministerský rada"},{"type":"143","abbrev":"VVR","text":"vrchní vládní rada"},{"type":"212","abbrev":"OVRF","text":"odborný/vrchní referent"},{"type":"221","abbrev":"VRFR","text":"vrchní referent/rada"},{"type":"231","abbrev":"RORA","text":"rada/odborný rada"},{"type":"232","abbrev":"RMRA","text":"rada/ministerský rada"},{"type":"233","abbrev":"RVLR","text":"rada/vládní rada"}]
