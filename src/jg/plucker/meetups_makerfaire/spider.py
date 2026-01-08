import re
from datetime import date, datetime, time
from typing import Generator
from zoneinfo import ZoneInfo

from scrapy import Request, Spider as BaseSpider
from scrapy.http import TextResponse

from jg.plucker.items import Meetup


PRAGUE_TZ = ZoneInfo("Europe/Prague")


class Spider(BaseSpider):
    name = "meetups-makerfaire"

    start_urls = ["https://makerfaire.cz/"]

    min_items = 0

    def parse(
        self, response: TextResponse, today: date | None = None
    ) -> Generator[Request, None, None]:
        today = today or date.today()
        self.logger.info(f"Parsing {response.url}, today is {today}")
        
        # Extract city URLs from the index page
        city_links = response.xpath(
            '//a[contains(@class, "homepage__event")]/@href'
        ).getall()
        
        self.logger.debug(f"Found {len(city_links)} city links")
        
        for link in city_links:
            url = response.urljoin(link)
            self.logger.debug(f"Following city link: {url}")
            yield Request(url=url, callback=self.parse_city, cb_kwargs={"today": today})

    def parse_city(
        self, response: TextResponse, today: date
    ) -> Generator[Meetup, None, None]:
        # Extract city name from heading
        city_title = response.xpath('//h1[@class="brxe-heading"]/text()').get()
        if not city_title:
            self.logger.error(f"Could not find city title at {response.url}")
            return
        
        # Extract the city name from "Maker Faire <City>"
        city_match = re.search(r"Maker Faire (.+)", city_title)
        if not city_match:
            self.logger.error(f"Could not parse city from title: {city_title}")
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
            '//div[contains(@class, "city-hero__place")]//div[@class="brxe-text-basic"]/text()'
        ).get()
        if not address_text:
            self.logger.error(f"Could not find address at {response.url}")
            return
        
        # Full location includes both venue and city
        location = f"{address_text}, {city_name}"
        
        # Extract time if available
        time_text = response.xpath(
            '//div[contains(@class, "city-hero__time")]/text()'
        ).get()
        
        # Parse dates and create meetup items
        meetups = self.parse_dates(
            date_text, time_text, city_title, location, response.url, today
        )
        
        yield from meetups

    def parse_dates(
        self,
        date_text: str,
        time_text: str | None,
        title: str,
        location: str,
        source_url: str,
        today: date,
    ) -> Generator[Meetup, None, None]:
        """Parse date text and create meetup items for each day."""
        self.logger.debug(f"Parsing dates: {date_text}, time: {time_text}")
        
        # Parse time if available (format: "10:00–17:00" or "10:00 - 17:00")
        start_time = None
        end_time = None
        if time_text:
            time_match = re.search(r"(\d{1,2}):(\d{2})\s*[–-]\s*(\d{1,2}):(\d{2})", time_text)
            if time_match:
                start_time = time(int(time_match.group(1)), int(time_match.group(2)))
                end_time = time(int(time_match.group(3)), int(time_match.group(4)))
        
        # Parse date range
        # Format examples: "17.–18. října 2026", "23. května 2026", "19. dubna 2026"
        
        # Try single date first
        single_date_match = re.match(r"(\d{1,2})\.\s+(\w+)\s+(\d{4})", date_text)
        if single_date_match:
            day = int(single_date_match.group(1))
            month_name = single_date_match.group(2)
            year = int(single_date_match.group(3))
            month = self.parse_czech_month(month_name)
            
            event_date = date(year, month, day)
            if event_date < today:
                self.logger.debug(f"Past event: {title} {event_date}")
                return
            
            starts_at = datetime.combine(event_date, start_time or time(0, 0))
            starts_at = starts_at.replace(tzinfo=PRAGUE_TZ)
            
            if end_time:
                ends_at = datetime.combine(event_date, end_time)
                ends_at = ends_at.replace(tzinfo=PRAGUE_TZ)
            else:
                ends_at = None
            
            self.logger.info(f"Event: {title} {starts_at}")
            yield Meetup(
                title=title,
                url=source_url,
                description=None,
                starts_at=starts_at,
                ends_at=ends_at,
                location=location,
                source_url=source_url,
                series_name="Maker Faire",
                series_org="komunita tvůrců a kutilů",
                series_url="https://makerfaire.cz/",
            )
            return
        
        # Try date range (e.g., "17.–18. října 2026" or "9.–10. května 2026")
        range_match = re.match(
            r"(\d{1,2})\.–(\d{1,2})\.\s+(\w+)\s+(\d{4})", date_text
        )
        if range_match:
            start_day = int(range_match.group(1))
            end_day = int(range_match.group(2))
            month_name = range_match.group(3)
            year = int(range_match.group(4))
            month = self.parse_czech_month(month_name)
            
            # Create events for each day
            for day_num in range(start_day, end_day + 1):
                event_date = date(year, month, day_num)
                if event_date < today:
                    self.logger.debug(f"Past event: {title} {event_date}")
                    continue
                
                day_index = day_num - start_day + 1
                total_days = end_day - start_day + 1
                day_title = f"{title} ({day_index}. den)"
                
                starts_at = datetime.combine(event_date, start_time or time(0, 0))
                starts_at = starts_at.replace(tzinfo=PRAGUE_TZ)
                
                if end_time:
                    ends_at = datetime.combine(event_date, end_time)
                    ends_at = ends_at.replace(tzinfo=PRAGUE_TZ)
                else:
                    ends_at = None
                
                self.logger.info(f"Event: {day_title} {starts_at}")
                yield Meetup(
                    title=day_title,
                    url=source_url,
                    description=None,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    location=location,
                    source_url=source_url,
                    series_name="Maker Faire",
                    series_org="komunita tvůrců a kutilů",
                    series_url="https://makerfaire.cz/",
                )
            return
        
        self.logger.error(f"Could not parse date: {date_text}")

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
        return months.get(month_name.lower(), 1)
