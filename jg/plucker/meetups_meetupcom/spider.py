from typing import Generator

import teemup
from scrapy import Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-meetupcom"

    min_items = 1

    start_urls = [
        "https://www.meetup.com/pydata-prague/events/",
        "https://www.meetup.com/reactgirls/events/",
        "https://www.meetup.com/frontendisti/events/",
        "https://www.meetup.com/pehapkari/events/",
        "https://www.meetup.com/pehapkari-brno/events/",
        "https://www.meetup.com/professionaltesting/events/",
        "https://www.meetup.com/protest_cz/events/",
        "https://www.meetup.com/praguejs/events/",
        "https://www.meetup.com/techmeetupostrava/events/",
        "https://www.meetup.com/prague-gen-ai/events/",
        "https://www.meetup.com/brno-java-meetup/events/",
    ]

    def parse(self, response: TextResponse) -> Generator[Meetup, None, None]:
        self.logger.info(f"Parsing {response.url}")
        events = teemup.parse(response.text)
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (self.parse_event(response.url, event) for event in events)
        yield from filter(None, meetups)

    def parse_event(self, source_url: str, event: teemup.Event) -> Meetup | None:
        if venue := event["venue"]:
            venue_parts = [
                venue["name"],
                venue["address"],
                venue["city"],
                venue["state"],
                venue["country"].upper() if venue["country"] else None,
            ]
            location = ", ".join(filter(None, venue_parts))
            self.logger.info(f"Event: {event['title']} {event['starts_at']}")
            return Meetup(
                title=event["title"],
                url=event["url"],
                description=event["description"],
                starts_at=event["starts_at"],
                ends_at=event["ends_at"],
                location=location,
                source_url=source_url,
            )
        self.logger.debug(f"Event without venue: {event['title']} {event['starts_at']}")
