from typing import Generator, cast

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response
from scrapy.http.response.text import TextResponse

from jg.plucker.items import Company


class Spider(BaseSpider):
    name = "companies"

    start_urls = []

    start_urls = ["https://junior.guru/api/courses-up-business-ids.json"]

    custom_settings = {
        "USER_AGENT": "JuniorGuruBot (+https://junior.guru)",
    }

    def parse(self, response: Response) -> Generator[Request, None, None]:
        response = cast(TextResponse, response)
        business_ids: list[str] = response.json()
        for business_id in business_ids:
            yield Request(
                f"https://api.merk.cz/company/?country_code=cz&regno={business_id}",
                headers={
                    'Authorization': f'Token {self.settings["MERK_API_KEY"]}',
                },
                callback=self.parse_company,
            )

    def parse_company(self, response: Response) -> Company:
        response = cast(TextResponse, response)
        data = response.json()
        return Company(
            name=data["name"],
        )
