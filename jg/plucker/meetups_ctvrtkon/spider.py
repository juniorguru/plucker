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
        for event in events:
            starts_at = datetime.fromisoformat(event["started_at"]).replace(
                tzinfo=ZoneInfo("Europe/Prague")
            )
            if starts_at.date() < today:
                self.logger.debug(f"Past event: {event['name']} {starts_at}")
            else:
                self.logger.info(f"Event: {event['name']} {starts_at}")
                yield Meetup(
                    title=event["name"],
                    url=f"https://ctvrtkon.cz/public/udalost/{event['slug']}",
                    description=event["description"],
                    starts_at=starts_at,
                    ends_at=datetime.fromisoformat(event["ended_at"]).replace(
                        tzinfo=ZoneInfo("Europe/Prague")
                    ),
                    location=f"{event['venue']['name']}, {event['venue']['address']}",
                    source_url=response.url,
                )
