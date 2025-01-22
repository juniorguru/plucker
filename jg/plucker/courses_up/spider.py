import json
from enum import IntEnum, unique
from pprint import pformat
from typing import Generator

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response.text import TextResponse

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
    custom_settings = {"AUTOTHROTTLE_ENABLED": False}

    def parse(self, response: TextResponse) -> Generator[Request, None, None]:
        self.logger.info("Acquired cookies")
        self.logger.info(
            f"Querying courses of {len(CourseType)} types "
            f"which are in {len(CourseCategory)} categories"
        )
        for course_type in sorted(CourseType):
            for course_category in sorted(CourseCategory):
                yield self.fetch_courses(course_type, course_category)

    def fetch_courses(
        self,
        course_type: CourseType,
        course_category: CourseCategory,
        start: int = 0,
        step: int = 120,
    ) -> Request:
        self.logger.info(
            f"Fetching courses from {start} to {start + step} ({course_type}/{course_category})"
        )
        return Request(
            "https://www.uradprace.cz/api/rekvalifikace/rest/kurz/query-ex",
            method="POST",
            headers={
                "Accept": "application/json",
                "Accept-Language": "cs",
                "Content-Type": "application/json",
            },
            body=json.dumps(
                {
                    "optKurzIds": False,
                    "optDruhKurzu": False,
                    "optNazevKurzu": False,
                    "optKodKurzu": False,
                    "optStavKurzu": False,
                    "optStavZajmu": False,
                    "optNazevVzdelavatele": False,
                    "optIcoVzdelavatele": False,
                    "optKategorie": True,
                    "kategorieId": int(course_category),
                    "optAkreditace": False,
                    "pagination": {"start": start, "count": step, "order": ["-id"]},
                    "optFormaVzdelavaniIds": False,
                    "optTermin": False,
                    "optCena": False,
                    "optJazykIds": False,
                    "optMistoKonani": False,
                    "optTypKurzuIds": True,
                    "typKurzuIds": [int(course_type)],
                }
            ),
            dont_filter=True,
            callback=self.parse_courses,
            cb_kwargs={
                "course_type": course_type,
                "course_category": course_category,
                "next_start": start + step,
            },
        )

    def parse_courses(
        self,
        response: TextResponse,
        course_type: CourseType,
        course_category: CourseCategory,
        next_start: int,
    ) -> Generator[CourseProvider | Request, None, None]:
        data = json.loads(response.body)
        if count := len(data["list"]):
            self.logger.info(
                f"Processing {count} courses of {data['count']} ({course_type}/{course_category})"
            )
            for course in data["list"]:
                try:
                    yield CourseProvider(
                        id=course["id"],
                        url=(
                            "https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu"
                            f"#/rekvalifikacni-kurz-detail/{course['id']}"
                        ),
                        name=course["nazev"],
                        description=course["popisRekvalifikace"],
                        company_name=course["osoba"]["nazev"],
                        cz_business_id=int(course["osoba"]["ico"].lstrip("0")),
                    )
                except KeyError:
                    self.logger.error(f"Failed to parse:\n{pformat(course)}")
                    raise
            yield self.fetch_courses(course_type, course_category, next_start)
        else:
            self.logger.info(
                f"Seems like all {data['count']} courses are done ({course_type}/{course_category})"
            )
