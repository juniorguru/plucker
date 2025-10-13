import json
from datetime import date, datetime
from typing import Generator
from zoneinfo import ZoneInfo

from scrapy import Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-ctvrtkon"

    start_urls = ["https://ctvrtkon.cz/api/events/feed"]

    min_items = 0

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Meetup, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        events = json.loads(response.text)["data"]
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (self.parse_event(response.url, today, event) for event in events)
        yield from filter(None, meetups)

    def parse_event(self, source_url: str, today: date, event: dict) -> Meetup | None:
        starts_at = datetime.fromisoformat(event["started_at"]).replace(
            tzinfo=ZoneInfo("Europe/Prague")
        )

        if starts_at.date() < today:
            self.logger.debug(f"Past event: {event['name']} {starts_at}")
            return

        self.logger.info(f"Event: {event['name']} {starts_at}")
        return Meetup(
            title=event["name"],
            url=f"https://ctvrtkon.cz/public/udalost/{event['slug']}",
            description=event["description"],
            starts_at=starts_at,
            ends_at=datetime.fromisoformat(event["ended_at"]).replace(
                tzinfo=ZoneInfo("Europe/Prague")
            ),
            location=f"{event['venue']['name']}, {event['venue']['address']}",
            source_url=source_url,
            series_name="Čtvrtkon",
            series_org="místní IT komunita",
            series_url="https://ctvrtkon.cz/",
        )
