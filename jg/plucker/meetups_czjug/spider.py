import re
from datetime import date
from typing import Generator

from ics import Calendar
from scrapy import Request, Spider as BaseSpider
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
    ) -> Generator[Request | Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        calendar = Calendar(response.text)
        self.logger.debug(f"Total events: {len(calendar.events)}")
        for event in calendar.events:
            if not event.location or event.location.startswith("http"):
                self.logger.debug(
                    f"Event without location: {event.summary} {event.begin}"
                )
            elif match := self.meetup_com_url_re.search(event.description or ""):
                self.logger.debug(
                    f"Meetup.com event: {event.summary} {event.begin} ({match.group(0)} found in {event.description!r})"
                )
            elif "BrnoJUG" in (event.summary or ""):
                self.logger.debug(
                    f"Meetup.com event: {event.summary} {event.begin} (BrnoJUG)"
                )
            elif event.begin and event.begin.date() < today:
                self.logger.debug(f"Past event: {event.summary} {event.begin}")
            else:
                if match := self.jug_url_re.search(event.description or ""):
                    url = match.group(0)
                else:
                    url = self.default_event_url
                self.logger.info(f"Event: {event.summary} {event.begin}")
                yield Meetup(
                    title=event.summary,
                    url=url,
                    description=event.description,
                    starts_at=event.begin,
                    ends_at=event.end,
                    location=event.location,
                    source_url=response.url,
                )
