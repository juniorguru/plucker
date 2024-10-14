from datetime import date
from typing import Generator

from ics import Calendar
from scrapy import Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-pyvo"

    start_urls = ["https://pyvo.cz/api/pyvo.ics"]

    min_items = 1

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        calendar = Calendar(response.text)
        self.logger.debug(f"Total events: {len(calendar.events)}")
        for event in calendar.events:
            if event.begin and event.begin.date() < today:
                self.logger.debug(f"Past event: {event.summary} {event.begin}")
            elif "tentative-date" in event.categories:
                self.logger.debug(f"Tentative event: {event.summary} {event.begin}")
            else:
                self.logger.info(f"Event: {event.summary} {event.begin}")
                yield Meetup(
                    title=event.summary,
                    url=event.url,
                    description=event.description,
                    starts_at=event.begin,
                    ends_at=event.end,
                    location=event.location,
                    source_url=response.url,
                )
