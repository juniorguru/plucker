import json
from enum import IntEnum, unique
from pprint import pformat
from typing import Generator

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

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

    start_urls = ["https://junior.guru"]  # TODO

    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 2,
        "RETRY_TIMES": 5,
        "HTTPCACHE_EXPIRATION_SECS": 151200,  # 42 hours
    }

    def parse(self, response: Response) -> Generator[Request, None, None]:
        business_ids = [  # TODO
            "01018329",
            "02559226",
            "03888509",
            "04380011",
            "04671317",
            "05630631",
            "05861381",
            "06222447",
            "06446710",
            "07513666",
            "09587535",
            "09863427",
            "10827161",
            "14064570",
            "14143801",
            "14389762",
            "17163587",
            "17163587",
            "17321743",
            "17519039",
            "22746668",
            "22746668",
            "22746668",
            "22834958",
            "24146692",
            "25110853",
            "26441381",
            "26502275",
            "27914950",
            "28128842",
            "61989100",
            "69320144",
        ]
        yield Request(
            "https://www.uradprace.cz/web/cz/vyhledani-rekvalifikacniho-kurzu",
            self.parse_cookies,
            cb_kwargs={"business_ids": business_ids},
        )

    def parse_cookies(
        self, response: Response, business_ids: list[str]
    ) -> Generator[Request, None, None]:
        self.logger.info("Acquired cookies")
        self.logger.info(
            f"Querying courses provided by {len(business_ids)} "
            f"of {len(CourseType)} types "
            f"which are in {len(CourseCategory)} categories"
        )
        for business_id in business_ids:
            for course_category in sorted(CourseCategory):
                yield self.fetch_courses(business_id, course_category)

    def fetch_courses(
        self,
        business_id: str,
        course_category: CourseCategory,
        start: int = 0,
        step: int = 30,
    ) -> Request:
        self.logger.info(
            f"Fetching courses from {start} to {start + step} (category {course_category})"
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
                    "icoVzdelavatele": business_id,
                    "optKurzIds": False,
                    "optDruhKurzu": False,
                    "optNazevKurzu": False,
                    "optKodKurzu": False,
                    "optStavKurzu": False,
                    "optStavZajmu": False,
                    "optNazevVzdelavatele": False,
                    "optIcoVzdelavatele": True,
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
                    "typKurzuIds": sorted(map(int, CourseType)),
                }
            ),
            dont_filter=True,
            callback=self.parse_courses,
            cb_kwargs={
                "business_id": business_id,
                "course_category": course_category,
                "next_start": start + step,
            },
        )

    def parse_courses(
        self,
        response: Response,
        business_id: str,
        course_category: CourseCategory,
        next_start: int,
    ) -> Generator[CourseProvider | Request, None, None]:
        data = json.loads(response.body)
        print(data)
        if count := len(data["list"]):
            self.logger.info(
                f"Processing {count} courses of {data['count']} "
                f"(business ID: {business_id}, category {course_category})"
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
                except KeyError as e:
                    self.logger.error(f"Failed to parse:\n{pformat(course)}")
                    raise
            if count == data["count"]:
                self.logger.info(
                    f"Seems like all {data['count']} courses are done (category {course_category})"
                )
            else:
                yield self.fetch_courses(business_id, course_category, next_start)
        else:
            self.logger.info(
                f"Seems like all {data['count']} courses are done (category {course_category})"
            )
