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
        if api_key := self.settings.get("MERK_API_KEY"):
            response = cast(TextResponse, response)
            course_providers: list[dict] = response.json()
            self.logger.info(f"Fetched {len(course_providers)} course providers")
            for country_code in ["cz", "sk"]:
                self.logger.info(
                    f"Filtering course providers for {country_code.upper()} "
                    f"({len(course_providers)} total)"
                )
                business_ids = sorted(
                    course_provider[f"{country_code}_business_id"]
                    for course_provider in course_providers
                    if course_provider[f"{country_code}_business_id"]
                )
                self.logger.info(
                    f"Found {len(business_ids)} course providers "
                    f"with {country_code.upper()} business IDs"
                )
                if business_ids:
                    yield Request(
                        "https://api.merk.cz/company/mget/",
                        method="POST",
                        headers={
                            "Authorization": f"Token {api_key}",
                            "Content-Type": "application/json",
                        },
                        body=json.dumps(
                            {"country_code": country_code, "regnos": business_ids}
                        ),
                        callback=self.parse_companies,
                        cb_kwargs={"country_code": country_code},
                    )
        else:
            raise ValueError("Missing MERK_API_KEY environment variable")

    def parse_companies(
        self, response: Response, country_code: str
    ) -> Generator[Company, None, None]:
        response = cast(TextResponse, response)
        for data in response.json():
            yield Company(
                name=data["name"],
                country_code=country_code,
                business_id=data["regno"],
                legal_form=data["legal_form"]["text"],
                years_in_business=data["years_in_business"],
                # TODO: address, turnover, insolvency_cases, magnitude, emails, is_active,
                # government_grants, gps, linkedin, twitter, facebook, sk_insolvency_cases
            )
