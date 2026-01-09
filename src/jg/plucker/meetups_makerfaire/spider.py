import re
from datetime import date, datetime, time
from typing import Generator
from zoneinfo import ZoneInfo

from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


class Spider(BaseSpider):
    name = "meetups-makerfaire"

    start_urls = ["https://makerfaire.cz/"]

    min_items = 5

    prague_tz = ZoneInfo("Europe/Prague")

    def parse(self, response: TextResponse) -> Generator[Request, None, None]:
        self.logger.debug(f"Parsing {response.url}")
        # Extract city URLs from the index page
        city_links = response.xpath(
            '//a[contains(@class, "homepage__event")]/@href'
        ).getall()
        self.logger.info(f"Found {len(city_links)} city links")

        for link in city_links:
            url = response.urljoin(link)
            self.logger.debug(f"Following city link: {url}")
            yield Request(url=url, callback=self.parse_city)

    def parse_city(self, response: TextResponse) -> Generator[Meetup, None, None]:
        # Extract city name from heading
        city_title = response.xpath('//h1[@class="brxe-heading"]/text()').get()
        if not city_title:
            self.logger.error(f"Could not find city title at {response.url}")
            return

        # Extract the city name from "Maker Faire <City>"
        city_match = re.search(r"Maker Faire (.+)", city_title)
        if not city_match:
            self.logger.error(f"Could not parse city from title: {city_title!r}")
            return
        city_name = city_match.group(1)

        # Extract date range
        date_text = response.xpath(
            '//div[contains(@class, "city-hero__date")]/text()'
        ).get()
        if not date_text:
            self.logger.error(f"Could not find date at {response.url}")
            return

        # Extract address/venue
        address_text = response.xpath(
            '//a[contains(@class, "city-hero__place")]//text()'
        ).get()
        if not address_text:
            self.logger.error(f"Could not find address at {response.url}")
            return
        address_text = address_text.strip()

        # Full location includes both venue and city
        location = f"{address_text}, {city_name}"

        # Extract time if available
        time_text_nodes = response.xpath(
            '//div[contains(@class, "city-hero__time")]/text()'
        ).getall()
        time_text = next(
            (text.strip() for text in time_text_nodes if ":" in text),
            None,
        )

        # Parse dates and create meetup items
        yield from self.parse_dates(
            date_text, time_text, city_title, location, response.url
        )

    def parse_dates(
        self,
        date_text: str,
        time_text: str | None,
        title: str,
        location: str,
        source_url: str,
    ) -> Generator[Meetup, None, None]:
        """Parse date text and create meetup items for each day."""
        self.logger.debug(f"Parsing dates: {date_text}, time: {time_text}")

        # Parse time if available
        start_time, end_time = self.parse_time(time_text)

        # Parse date - split into parts: day(s), month, year
        # Format examples: "17.–18. října 2026", "23. května 2026", "19. dubna 2026"

        # Try single date first
        if single_date_match := re.match(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})", date_text):
            day = int(single_date_match.group(1))
            month_name = single_date_match.group(2)
            year = int(single_date_match.group(3))
            month = self.parse_czech_month(month_name)

            yield self.create_meetup(
                title, location, source_url, year, month, day, start_time, end_time
            )
            return

        # Try date range (e.g., "17.–18. října 2026" or "9.–10. května 2026")
        if range_match := re.match(
            r"(\d{1,2})\.–(\d{1,2})\.\s+(\w+)\s+(\d{4})", date_text
        ):
            start_day = int(range_match.group(1))
            end_day = int(range_match.group(2))
            month_name = range_match.group(3)
            year = int(range_match.group(4))
            month = self.parse_czech_month(month_name)

            # Create events for each day
            for day_num in range(start_day, end_day + 1):
                day_index = day_num - start_day + 1
                day_title = f"{title} ({day_index}. den)"

                yield self.create_meetup(
                    day_title,
                    location,
                    source_url,
                    year,
                    month,
                    day_num,
                    start_time,
                    end_time,
                )
            return

        raise ValueError(f"Could not parse date: {date_text}")

    def parse_time(self, time_text: str | None) -> tuple[time | None, time | None]:
        """Parse time text (format: "10:00–17:00" or "10:00 - 17:00")."""
        if not time_text:
            return None, None

        time_match = re.search(
            r"(\d{1,2}):(\d{2})\s*[–\u2013\u2014-]\s*(\d{1,2}):(\d{2})", time_text
        )
        if time_match:
            start_time = time(int(time_match.group(1)), int(time_match.group(2)))
            end_time = time(int(time_match.group(3)), int(time_match.group(4)))
            return start_time, end_time

        raise ValueError(f"Could not parse time: {time_text}")

    def create_meetup(
        self,
        title: str,
        location: str,
        source_url: str,
        year: int,
        month: int,
        day: int,
        start_time: time | None,
        end_time: time | None,
    ) -> Meetup:
        """Create a meetup item with the given parameters."""
        event_date = date(year, month, day)
        starts_at = datetime.combine(
            event_date, start_time or time(0, 0), tzinfo=self.prague_tz
        )
        ends_at = (
            datetime.combine(event_date, end_time, tzinfo=self.prague_tz)
            if end_time
            else None
        )

        self.logger.info(f"Event: {title} {starts_at}")
        return Meetup(
            title=title,
            url=source_url,
            description=None,
            starts_at=starts_at,
            ends_at=ends_at,
            location=location,
            source_url=source_url,
            series_name="Maker Faire",
            series_org="komunita technologických kutilů",
            series_url="https://makerfaire.cz/",
        )

    def parse_czech_month(self, month_name: str) -> int:
        """Convert Czech month name to month number."""
        months = {
            "ledna": 1,
            "února": 2,
            "března": 3,
            "dubna": 4,
            "května": 5,
            "června": 6,
            "července": 7,
            "srpna": 8,
            "září": 9,
            "října": 10,
            "listopadu": 11,
            "prosince": 12,
        }
        try:
            return months[month_name.lower()]
        except KeyError:
            raise ValueError(f"Unsupported Czech month name: {month_name}")
