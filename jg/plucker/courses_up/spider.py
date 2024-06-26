import json
from enum import IntEnum, unique
from pprint import pformat
from typing import Generator

from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import CourseProvider


@unique
class CourseCategory(IntEnum):
    COMPUTER_COURSES = 10115
    INTERNET = 10124
    WEB_PAGES = 10125
    WEB_DESIGN = 10126
    E_COMMERCE = 10127
    OTHER_INTERNET = 10128
    OPERATING_SYSTEMS = 10116
    OPERATING_SYSTEMS_COMPUTERS = 10117
    OPERATING_SYSTEMS_MOBILE = 10118
    OPERATING_SYSTEMS_SERVERS = 10119
    OPERATING_SYSTEMS_OTHER = 10120
    NETWORKING_AND_SERVERS = 10123
    PROGRAMMING = 10130
    DATA = 10131
    SECURITY = 10140


@unique
class CourseType(IntEnum):
    SECURED_REQUALIFICATION = 10078
    CHOSEN_REQUALIFICATION = 10079
    COURSE = 10080


class Spider(BaseSpider):
    name = "courses-up"
    start_urls = ["https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu"]
    course_types = sorted(map(int, CourseType))
    course_categories = sorted(map(int, CourseCategory))

    def parse(self, response: TextResponse) -> Request:
        self.logger.info("Acquired cookies")
        self.logger.info(
            f"Querying courses of {len(self.course_types)} types "
            f"which are in {len(self.course_categories)} categories"
        )
        return self.fetch_courses()

    def fetch_courses(self, start: int = 0, step: int = 100) -> Request:
        self.logger.info(f"Fetching courses from {start} to {start + step}")
        return Request(
            "https://www.uradprace.cz/api/rekvalifikace/rest/kurz/query",
            method="POST",
            headers={
                "Accept": "application/json",
                "Accept-Language": "cs",
                "DNT": "1",
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {
                    "index": ["rekvalifikace"],
                    "pagination": {"start": start, "count": step, "order": ["-id"]},
                    "query": {
                        "must": [
                            {
                                "matchAny": {
                                    "field": "typRekvalifikaceId",
                                    "query": self.course_types,
                                }
                            },
                            {
                                "matchAny": {
                                    "field": "kategorie.kategorieId",
                                    "query": self.course_categories,
                                }
                            },
                        ]
                    },
                }
            ),
            dont_filter=True,
            callback=self.parse_courses,
            cb_kwargs={"next_start": start + step},
        )

    def parse_courses(
        self, response: TextResponse, next_start: int
    ) -> Generator[CourseProvider | Request, None, None]:
        data = json.loads(response.body)
        if count := len(data["list"]):
            self.logger.info(f"Processing {count} courses")
            for course in data["list"]:
                try:
                    yield CourseProvider(
                        id=course["id"],
                        url=f"https://www.uradprace.cz/rekvalifikace/kurz/{course['id']}",
                        name=course["nazev"],
                        description=course["popisRekvalifikace"],
                        company_name=course["osoba"]["nazev"],
                        cz_business_id=int(course["osoba"]["ico"].lstrip("0")),
                    )
                except KeyError:
                    self.logger.error(f"Failed to parse:\n{pformat(course)}")
                    raise
            yield self.fetch_courses(next_start)
        else:
            self.logger.info(f'Seems like all {data["count"]} courses are done')
