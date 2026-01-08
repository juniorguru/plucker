from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from scrapy.http.response.html import HtmlResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_makerfaire.spider import Spider


FIXTURES_DIR = Path(__file__).parent / "meetups_makerfaire"
PRAGUE_TZ = ZoneInfo("Europe/Prague")


def test_parse_index():
    """Test parsing the index page to extract city links."""
    response = HtmlResponse(
        "https://makerfaire.cz/",
        body=Path(FIXTURES_DIR / "index.html").read_bytes(),
    )
    requests = list(Spider().parse(response, today=date(2025, 1, 1)))
    
    # Should have at least some city links
    assert len(requests) > 0
    # Check that we're following city pages
    assert any("brno" in str(req.url) or "makerfaire.cz" in str(req.url) for req in requests)


def test_parse_brno_two_day_event():
    """Test parsing Brno detail page with 2-day event without time."""
    response = HtmlResponse(
        "https://makerfaire.cz/brno/",
        body=Path(FIXTURES_DIR / "brno.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response, today=date(2025, 1, 1)))
    
    # Should create 2 meetups for 2-day event (17.–18. října 2026)
    assert len(meetups) == 2
    
    # Check first day
    meetup1 = meetups[0]
    assert isinstance(meetup1, Meetup)
    assert meetup1["title"] == "Maker Faire Brno (1. den)"
    assert meetup1["location"] == "Brněnské výstaviště, Brno"
    assert meetup1["url"] == "https://makerfaire.cz/brno/"
    assert meetup1["source_url"] == "https://makerfaire.cz/brno/"
    assert meetup1["series_name"] == "Maker Faire"
    assert meetup1["series_org"] == "komunita tvůrců a kutilů"
    assert meetup1["series_url"] == "https://makerfaire.cz/"
    
    # Check date for first day (October 17, 2026)
    starts_at = meetup1["starts_at"]
    assert starts_at.year == 2026
    assert starts_at.month == 10
    assert starts_at.day == 17
    assert starts_at.tzinfo == PRAGUE_TZ
    
    # When no time is specified, should use midnight
    assert starts_at.hour == 0
    assert starts_at.minute == 0
    assert meetup1["ends_at"] is None
    
    # Check second day
    meetup2 = meetups[1]
    assert meetup2["title"] == "Maker Faire Brno (2. den)"
    assert meetup2["location"] == "Brněnské výstaviště, Brno"
    starts_at2 = meetup2["starts_at"]
    assert starts_at2.year == 2026
    assert starts_at2.month == 10
    assert starts_at2.day == 18


def test_parse_ostrava_single_day_with_time():
    """Test parsing Ostrava detail page with single-day event with time."""
    response = HtmlResponse(
        "https://makerfaire.cz/ostrava/",
        body=Path(FIXTURES_DIR / "detail-time.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response, today=date(2025, 1, 1)))
    
    # Should create 1 meetup for single-day event (19. dubna 2026)
    assert len(meetups) == 1
    
    meetup = meetups[0]
    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Ostrava"
    assert meetup["location"] == "Dolní oblast Vítkovice, Ostrava"
    assert meetup["url"] == "https://makerfaire.cz/ostrava/"
    assert meetup["source_url"] == "https://makerfaire.cz/ostrava/"
    
    # Check date (April 19, 2026, 10:00-17:00)
    starts_at = meetup["starts_at"]
    assert starts_at.year == 2026
    assert starts_at.month == 4
    assert starts_at.day == 19
    assert starts_at.hour == 10
    assert starts_at.minute == 0
    assert starts_at.tzinfo == PRAGUE_TZ
    
    # Check end time
    ends_at = meetup["ends_at"]
    assert ends_at is not None
    assert ends_at.hour == 17
    assert ends_at.minute == 0
    assert ends_at.tzinfo == PRAGUE_TZ


def test_timezone_conversion_to_utc():
    """Test that datetime is in Europe/Prague timezone (will be converted to UTC by Scrapy)."""
    response = HtmlResponse(
        "https://makerfaire.cz/brno/",
        body=Path(FIXTURES_DIR / "brno.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response, today=date(2025, 1, 1)))
    
    assert len(meetups) > 0
    meetup = meetups[0]
    
    # Check that timezone is Europe/Prague
    assert meetup["starts_at"].tzinfo == PRAGUE_TZ


def test_past_events_filtered():
    """Test that past events are filtered out."""
    response = HtmlResponse(
        "https://makerfaire.cz/brno/",
        body=Path(FIXTURES_DIR / "brno.html").read_bytes(),
    )
    # Set today to after the event
    meetups = list(Spider().parse_city(response, today=date(2026, 12, 1)))
    
    # Should not return any meetups as the event is in the past
    assert len(meetups) == 0
