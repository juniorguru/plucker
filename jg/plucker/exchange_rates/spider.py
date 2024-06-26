from datetime import date, timedelta
from decimal import Decimal
from typing import Generator

from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import ExchangeRate


class Spider(BaseSpider):
    name = "exchange-rates"

    def start_requests(self) -> Generator[Request, None, None]:
        monday = get_last_monday(date.today())
        yield Request(
            "https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/"
            "denni_kurz.txt"
            f"?date={monday:%d.%m.%Y}"
        )

    def parse(self, response: TextResponse) -> Generator[ExchangeRate, None, None]:
        for line in parse_lines(response.text):
            yield ExchangeRate(**parse_exchange_rate(line))


def get_last_monday(today) -> date:
    return today - timedelta(days=today.weekday())


def parse_exchange_rate(line) -> dict[str, str | Decimal]:
    return dict(
        code=line.split("|")[3], rate=Decimal(line.split("|")[4].replace(",", "."))
    )


def parse_lines(text: str) -> list[str]:
    return text.strip().splitlines()[2:]
