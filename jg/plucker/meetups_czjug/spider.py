import re
from datetime import date
from typing import Generator

from ics import Calendar, Event
from scrapy import Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_meetupcom.spider import Spider as MeetupComSpider


class Spider(BaseSpider):
    name = "meetups-czjug"

    start_urls = [
        "https://calendar.google.com/calendar/ical/mjil9nmeva31du9eofmbpobdeo%40group.calendar.google.com/public/basic.ics"
    ]

    min_items = 0

    meetup_com_url_re = re.compile(
        r"|".join(
            re.escape(
                url.removeprefix("https://www.")
                .removesuffix("/")
                .removesuffix("/events")
            )
            for url in MeetupComSpider.start_urls
        ),
        re.IGNORECASE,
    )

    jug_url_re = re.compile(r"https?://(www\.)?jug\.cz/[^/]+/")

    default_event_url = "https://www.jug.cz/category/udalosti/"

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        events = Calendar(response.text).events
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (self.parse_event(response.url, today, event) for event in events)
        yield from filter(None, meetups)

    def parse_event(self, source_url: str, today: date, event: Event) -> Meetup | None:
        if not event.location or event.location.startswith("http"):
            self.logger.debug(f"Event without location: {event.summary} {event.begin}")
            return

        if match := self.meetup_com_url_re.search(event.description or ""):
            self.logger.debug(
                f"Meetup.com event: {event.summary} {event.begin} ({match.group(0)} found in {event.description!r})"
            )
            return

        if "BrnoJUG" in (event.summary or ""):
            self.logger.debug(
                f"Meetup.com event: {event.summary} {event.begin} (BrnoJUG)"
            )
            return

        if event.begin and event.begin.date() < today:
            self.logger.debug(f"Past event: {event.summary} {event.begin}")
            return

        self.logger.info(f"Event: {event.summary} {event.begin}")
        if match := self.jug_url_re.search(event.description or ""):
            url = match.group(0)
        else:
            url = self.default_event_url
        return Meetup(
            title=event.summary,
            url=url,
            description=event.description,
            starts_at=event.begin,
            ends_at=event.end,
            location=event.location,
            source_url=source_url,
        )
