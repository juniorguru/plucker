from datetime import date, datetime, timedelta
from typing import Generator
from zoneinfo import ZoneInfo

from ics import Calendar, Event
from scrapy import Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-pyvo"

    start_urls = ["https://pyvo.cz/api/pyvo.ics"]

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

        if "tentative-date" in event.categories:
            self.logger.debug(f"Tentative event: {event.summary} {event.begin}")
            return

        if not event.begin:
            raise ValueError(f"Event without start time: {event}")

        self.logger.info(f"Event: {event.summary} {event.begin}")
        default_ends_at = event.begin + timedelta(hours=3)

        return Meetup(
            title=event.summary,
            url=event.url,
            description=event.description,
            starts_at=as_prg_tz(event.begin),
            ends_at=as_prg_tz(max(event.end or default_ends_at, default_ends_at)),
            location=event.location,
            source_url=source_url,
            series_name="Pyvo",
            series_org="komunita kolem Pythonu",
            series_url="https://pyvo.cz/",
        )


def as_prg_tz(dt: datetime, tz: ZoneInfo = ZoneInfo("Europe/Prague")) -> datetime:
    return dt.astimezone(tz).replace(tzinfo=None)
