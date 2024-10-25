from typing import Generator, Iterable, NotRequired, TypedDict

import teemup
from scrapy import Spider as BaseSpider
from scrapy.http import Request, TextResponse

from jg.plucker.items import Meetup


class GroupSpec(TypedDict):
    name: NotRequired[str]
    description: str
    homepage_url: NotRequired[str]


GROUPS = {
    "https://www.meetup.com/pydata-prague/": {
        "description": "komunita kolem Pythonu a dat",
        "homepage_url": "https://pydata.cz/",
    },
    "https://www.meetup.com/reactgirls/": {
        "description": "komunita (nejen) žen kolem Reactu a frontendu",
        "homepage_url": "https://reactgirls.com/",
    },
    "https://www.meetup.com/frontendisti/": {
        "description": "komunita kolem frontendu",
        "homepage_url": "https://www.frontendisti.cz/",
    },
    "https://www.meetup.com/pehapkari/": {
        "description": "komunita kolem PHP",
        "homepage_url": "https://pehapkari.cz/",
    },
    "https://www.meetup.com/pehapkari-brno/": {
        "description": "komunita kolem PHP",
        "homepage_url": "https://pehapkari.cz/",
    },
    "https://www.meetup.com/professionaltesting/": {
        "description": "komunita kolem testování",
    },
    "https://www.meetup.com/protest_cz/": {
        "description": "komunita kolem testování",
        "homepage_url": "https://www.pro-test.info/",
    },
    "https://www.meetup.com/praguejs/": {
        "description": "komunita kolem JavaScriptu",
    },
    "https://www.meetup.com/techmeetupostrava/": {
        "description": "místní IT komunita",
        "homepage_url": "https://www.techmeetup.cz/",
    },
    "https://www.meetup.com/prague-gen-ai/": {
        "description": "komunita kolem AI",
    },
    "https://www.meetup.com/brno-java-meetup/": {
        "description": "komunita kolem Javy",
        "homepage_url": "https://www.jug.cz/",
    },
    "https://www.meetup.com/pyconsk/": {
        "description": "komunita kolem Pythonu",
        "homepage_url": "https://pycon.sk/",
    },
    "https://www.meetup.com/bratislava-react-meetup-group/": {
        "description": "komunita kolem Reactu",
    },
    "https://www.meetup.com/net-bratislava-meetup/": {
        "description": "komunita kolem .NETu",
    },
    "https://www.meetup.com/webup-web-developers-in-zilina/": {
        "description": "místní IT komunita",
    },
    "https://www.meetup.com/meetup-group-xlwhsgnm/": {
        "description": "komunita kolem Javy",
    },
    "https://www.meetup.com/wordpress-brno-meetups/": {
        "description": "komunita kolem WordPressu",
    },
}


class Spider(BaseSpider):
    name = "meetups-meetupcom"

    min_items = 1

    def start_requests(self) -> Iterable[Request]:
        for series_url in GROUPS:
            yield Request(
                f"{series_url.rstrip('/')}/events/",
                callback=self.parse,
                cb_kwargs={"series_url": series_url, "group": GROUPS[series_url]},
            )

    def parse(
        self, response: TextResponse, series_url: str, group: GroupSpec
    ) -> Generator[Meetup, None, None]:
        self.logger.info(f"Parsing {response.url}")
        events = teemup.parse(response.text)
        self.logger.debug(f"Total events: {len(events)}")
        meetups = (
            self.parse_event(response.url, event, series_url, group) for event in events
        )
        yield from filter(None, meetups)

    def parse_event(
        self,
        source_url: str,
        event: teemup.Event,
        series_url: str,
        group: GroupSpec,
    ) -> Meetup | None:
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
                series_name=group.get("name", event["group_name"]),
                series_org=group["description"],
                series_url=group.get("url", series_url),
            )
        self.logger.debug(f"Event without venue: {event['title']} {event['starts_at']}")
