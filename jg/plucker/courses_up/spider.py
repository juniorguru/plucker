import json
from pprint import pformat
from typing import Generator, cast

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response
from scrapy.http.response.text import TextResponse

from jg.plucker.items import CourseProvider


class Spider(BaseSpider):
    name = "courses-up"

    start_urls = ["https://junior.guru/api/courses-up-business-ids.json"]

    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2,
        "RETRY_TIMES": 5,
    }

    def parse(self, response: Response) -> Generator[Request, None, None]:
        response = cast(TextResponse, response)
        business_ids: list[str] = response.json()
        yield Request(
            "https://www.uradprace.cz/vyhledani-rekvalifikacniho-kurzu",
            self.parse_cookies,
            cb_kwargs={"business_ids": business_ids},
        )

    def parse_cookies(
        self, response: Response, business_ids: list[str]
    ) -> Generator[Request, None, None]:
        self.logger.info("Acquired cookies")
        self.logger.info(f"Querying courses provided by {len(business_ids)}")
        for business_id in business_ids:
            yield self.fetch_courses(business_id)

    def fetch_courses(
        self,
        business_id: str,
        start: int = 0,
        step: int = 30,
    ) -> Request:
        self.logger.info(
            f"Fetching courses from {start} to {start + step} (business ID: {business_id})"
        )
        return Request(
            f"https://www.uradprace.cz/api/rekvalifikace/rest/kurz/query-ex#{business_id}",
            method="POST",
            headers={
                "Accept": "application/json",
                "Accept-Language": "cs",
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {
                    "icoVzdelavatele": business_id,
                    "optKurzIds": False,
                    "optDruhKurzu": False,
                    "optNazevKurzu": False,
                    "optKodKurzu": False,
                    "optStavKurzu": False,
                    "optStavZajmu": False,
                    "optNazevVzdelavatele": False,
                    "optIcoVzdelavatele": True,
                    "optKategorie": False,
                    "optAkreditace": False,
                    "pagination": {"start": start, "count": step, "order": ["-id"]},
                    "optFormaVzdelavaniIds": False,
                    "optTermin": False,
                    "optCena": False,
                    "optJazykIds": False,
                    "optMistoKonani": False,
                    "optTypKurzuIds": False,
                }
            ),
            dont_filter=True,
            callback=self.parse_courses,
            cb_kwargs={"business_id": business_id, "next_start": start + step},
        )

    def parse_courses(
        self,
        response: Response,
        business_id: str,
        next_start: int,
    ) -> Generator[CourseProvider | Request, None, None]:
        data = json.loads(response.body)
        if count := len(data["list"]):
            self.logger.info(
                f"Processing {count} courses of {data['count']} (business ID: {business_id})"
            )
            for course in data["list"]:
                try:
                    if business_id != course["osoba"]["ico"]:
                        raise ValueError(
                            f"Business ID mismatch: {business_id} != {course['osoba']['ico']}"
                        )
                    yield CourseProvider(
                        id=course["id"],
                        url=(
                            "https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu"
                            f"#/rekvalifikacni-kurz-detail/{course['id']}"
                        ),
                        name=course["nazev"],
                        description=course["popisRekvalifikace"],
                        company_name=course["osoba"]["nazev"],
                        business_id=business_id,
                    )
                except KeyError:
                    self.logger.error(f"Failed to parse:\n{pformat(course)}")
                    raise
            if count == data["count"]:
                self.logger.info(
                    f"Seems like all {data['count']} courses are done (business ID: {business_id})"
                )
            else:
                yield self.fetch_courses(business_id, next_start)
        else:
            self.logger.info(
                f"Seems like all {data['count']} courses are done (business ID: {business_id})"
            )
