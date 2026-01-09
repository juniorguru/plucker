from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

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
    requests = list(Spider().parse(response))

    # Should have at least some city links
    assert len(requests) > 0

    # Check that specific city pages are included
    urls = [str(req.url) for req in requests]
    assert any("brno" in url for url in urls)
    assert any("ostrava" in url for url in urls)
    assert any("rychnov-nad-kneznou" in url for url in urls)


def test_parse_multi_day_event():
    """Test parsing detail page with 2-day event without time (Brno)."""
    response = HtmlResponse(
        "https://makerfaire.cz/brno/",
        body=Path(FIXTURES_DIR / "detail-multi-days.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

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
    assert starts_at.date() == date(2026, 10, 17)
    assert starts_at.time() == time(0, 0)
    assert starts_at.tzinfo == PRAGUE_TZ
    assert meetup1["ends_at"] is None

    # Check second day
    meetup2 = meetups[1]
    assert meetup2["title"] == "Maker Faire Brno (2. den)"
    assert meetup2["location"] == "Brněnské výstaviště, Brno"
    assert meetup2["starts_at"].date() == date(2026, 10, 18)


def test_parse_single_day_event():
    """Test parsing detail page with single-day event without time (Rychnov nad Kněžnou)."""
    response = HtmlResponse(
        "https://makerfaire.cz/rychnov-nad-kneznou/",
        body=Path(FIXTURES_DIR / "detail.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    # Should create 1 meetup for single-day event (19. dubna 2026)
    assert len(meetups) == 1

    meetup = meetups[0]
    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Rychnov nad Kněžnou"
    assert meetup["location"] == "Zámecká jízdárna, Rychnov nad Kněžnou"
    assert meetup["url"] == "https://makerfaire.cz/rychnov-nad-kneznou/"
    assert meetup["source_url"] == "https://makerfaire.cz/rychnov-nad-kneznou/"

    # Check date (April 19, 2026, no time specified)
    starts_at = meetup["starts_at"]
    assert starts_at.date() == date(2026, 4, 19)
    assert starts_at.time() == time(0, 0)
    assert starts_at.tzinfo == PRAGUE_TZ

    # No end time when not specified
    assert meetup["ends_at"] is None


def test_parse_single_day_with_time():
    """Test parsing detail page with single-day event with time (Ostrava)."""
    response = HtmlResponse(
        "https://makerfaire.cz/ostrava/",
        body=Path(FIXTURES_DIR / "detail-time.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    # Should create 1 meetup for single-day event (23. května 2026)
    assert len(meetups) == 1

    meetup = meetups[0]
    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Ostrava"
    assert meetup["location"] == "Trojhalí Karolina, Ostrava"
    assert meetup["url"] == "https://makerfaire.cz/ostrava/"
    assert meetup["source_url"] == "https://makerfaire.cz/ostrava/"

    # Check date (May 23, 2026, 10:00-17:00)
    starts_at = meetup["starts_at"]
    assert starts_at.date() == date(2026, 5, 23)
    assert starts_at.time() == time(10, 0)
    assert starts_at.tzinfo == PRAGUE_TZ

    # Check end time
    ends_at = meetup["ends_at"]
    assert ends_at is not None
    assert ends_at.time() == time(17, 0)
    assert ends_at.tzinfo == PRAGUE_TZ
