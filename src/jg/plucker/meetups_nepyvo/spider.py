from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from ics import Calendar, Event
from scrapy import Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import Meetup


SERIES_URL = "https://nepyvo.cz/"

PRAGUE_TZ = ZoneInfo("Europe/Prague")


class Spider(BaseSpider):
    name = "meetups-nepyvo"

    start_urls = ["https://nepyvo.cz/api/calendar/nepyvo.ics"]

    min_items = 0

    def parse(self, response: Response, today: date | None = None) -> Generator[Meetup]:
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
        starts_at = event.begin.replace(tzinfo=UTC)
        default_ends_at = starts_at + timedelta(hours=3)
        ends_at = max(
            (event.end.replace(tzinfo=UTC) if event.end else default_ends_at),
            default_ends_at,
        )

        return Meetup(
            title=event.summary,
            url=get_event_url(event.url, starts_at),
            description=event.description,
            starts_at=starts_at,
            ends_at=ends_at,
            location=event.location,
            source_url=source_url,
            series_name="NePyvo",
            series_org="komunita kolem Pythonu",
            series_url=SERIES_URL,
        )


def get_event_url(url: str | None, starts_at: datetime) -> str:
    """Returns a URL unique to the event, as junior.guru deduplicates meetups by URL

    The calendar has no per-event URLs and the website has no per-event pages,
    so the homepage URL gets UTM params with the event's date in Prague.
    """
    if url:
        return url
    starts_on = starts_at.astimezone(PRAGUE_TZ).date()
    params = {
        "utm_source": "juniorguru",
        "utm_medium": "club",
        "utm_campaign": f"meetup-{starts_on.isoformat()}",
    }
    return f"{SERIES_URL}?{urlencode(params)}"
