from datetime import date, timedelta, timezone
from typing import Generator

from ics import Calendar, Event
from scrapy import Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-nepyvo"

    start_urls = ["https://nepyvo.cz/api/calendar/nepyvo.ics"]

    min_items = 0

    def parse(
        self, response: Response, today: date | None = None
    ) -> Generator[Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        events = Calendar(response.text).events
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (self.parse_event(response.url, today, event) for event in events)
        yield from filter(None, meetups)

    def parse_event(self, source_url: str, today: date, event: Event) -> Meetup | None:
        if event.begin and event.begin.date() < today:
            self.logger.debug(f"Past event: {event.summary} {event.begin}")
            return

        if not event.begin:
            raise ValueError(f"Event without start time: {event}")

        self.logger.info(f"Event: {event.summary} {event.begin}")
        starts_at = event.begin.replace(tzinfo=timezone.utc)
        default_ends_at = starts_at + timedelta(hours=3)
        ends_at = max(
            (event.end.replace(tzinfo=timezone.utc) if event.end else default_ends_at),
            default_ends_at,
        )

        return Meetup(
            title=event.summary,
            url=event.url or "https://nepyvo.cz/",
            description=event.description,
            starts_at=starts_at,
            ends_at=ends_at,
            location=event.location,
            source_url=source_url,
            series_name="NePyvo",
            series_org="komunita kolem Pythonu",
            series_url="https://nepyvo.cz/",
        )
