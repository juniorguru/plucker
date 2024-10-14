from datetime import date
from operator import itemgetter
from typing import Generator, Iterable

from ics import Calendar, Event
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-pyvo"

    start_urls = ["https://pyvo.cz/api/pyvo.ics"]

    min_items_count = 10

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Request | Meetup, None, None]:
        today = today or date.today()
        calendar = Calendar(response.text)
        meetups = self.parse_events(response.url, calendar.events)
        meetups = sorted(meetups, key=itemgetter("starts_at"), reverse=True)
        for i, meetup in enumerate(meetups):
            if meetup["starts_at"].date() >= today or i <= self.min_items_count:
                self.logger.info(f"Meetup:\n{meetup!r}")
                yield meetup
            else:
                self.logger.debug(f"Past meetup:\n{meetup!r}")

    def parse_events(
        self, source_url: str, events: Iterable[Event]
    ) -> Generator[Meetup, None, None]:
        for event in events:
            if "tentative-date" in event.categories:
                self.logger.debug(f"Tentative event: {event.summary} {event.begin}")
            else:
                self.logger.debug(f"Event: {event.summary} {event.begin}")
                yield self.parse_event(source_url, event)

    def parse_event(self, source_url: str, event: Event) -> Meetup:
        return Meetup(
            title=event.summary,
            starts_at=event.begin,
            ends_at=event.end,
            location=event.location,
            url=event.url,
            source_url=source_url,
        )
