from datetime import date
from typing import Generator

from ics import Calendar
from lxml import html
from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-pehapkari"

    start_urls = [
        "https://calendar.google.com/calendar/ical/pehapkari.cz%40gmail.com/public/basic.ics"
    ]

    min_items = 0

    default_event_url = "https://pehapkari.cz/"

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Request | Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        events = Calendar(response.text).events
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (self.parse_event(response.url, today, event) for event in events)
        yield from filter(None, meetups)

    def parse_event(
        self, source_url: str, today: date, event
    ) -> Request | Meetup | None:
        if not event.location or event.location.startswith("http"):
            self.logger.debug(f"Event without location: {event.summary} {event.begin}")
            return

        if event.begin and event.begin.date() < today:
            self.logger.debug(f"Past event: {event.summary} {event.begin}")
            return

        self.logger.info(f"Event: {event.summary} {event.begin}")
        try:
            url = html.fromstring(event.description).xpath("//a/@href")[-1]
        except IndexError:
            url = self.default_event_url
        return Meetup(
            title=event.summary,
            url=url,
            description=event.description,
            starts_at=event.begin,
            ends_at=event.end,
            location=event.location,
            source_url=source_url,
            series_name="Péhápkaři",
            series_org="komunita kolem PHP",
            series_url="https://www.pehapkari.cz/",
        )
