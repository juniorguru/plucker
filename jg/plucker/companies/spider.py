import json
from typing import Generator, cast

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response
from scrapy.http.response.text import TextResponse

from jg.plucker.items import Company


class Spider(BaseSpider):
    name = "companies"

    start_urls = []

    start_urls = ["https://junior.guru/api/course-providers.json"]

    custom_settings = {
        "USER_AGENT": "JuniorGuruBot (+https://junior.guru)",
    }

    def parse(self, response: Response) -> Generator[Request, None, None]:
        response = cast(TextResponse, response)
        course_providers: list[dict] = response.json()
        self.logger.info(f"Fetched {len(course_providers)} course providers")
        request_bodies = [
            {
                "country_code": country_code,
                "regnos": [
                    course_provider[f"{country_code}_business_id"]
                    for course_provider in course_providers
                    if course_provider[f"{country_code}_business_id"]
                ],
            }
            for country_code in ["cz", "sk"]
        ]
        for request_body in request_bodies:
            if request_body["regnos"]:
                self.logger.info(
                    f"Querying {len(request_body['regnos'])} companies "
                    f"from {request_body['country_code'].upper()}"
                )
                yield Request(
                    "https://api.merk.cz/company/mget/",
                    method="POST",
                    headers={
                        "Authorization": f"Token {self.settings['MERK_API_KEY']}",
                        "Content-Type": "application/json",
                    },
                    body=json.dumps(request_body),
                    callback=self.parse_companies,
                )

    def parse_companies(self, response: Response) -> Generator[Company, None, None]:
        response = cast(TextResponse, response)
        for data in response.json():
            yield Company(
                name=data["name"],
            )
