from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from scrapy.http.response.html import HtmlResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_makerfaire.spider import Spider


FIXTURES_DIR = Path(__file__).parent


def test_parse_index():
    """Test parsing the index page to extract city links."""
    response = HtmlResponse(
        "https://makerfaire.cz/",
        body=Path(FIXTURES_DIR / "index.html").read_bytes(),
    )
    requests = list(Spider().parse(response))

    assert len(requests) > 0

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

    assert len(meetups) == 2

    # Check first day
    meetup1 = meetups[0]
    assert isinstance(meetup1, Meetup)
    assert meetup1["title"] == "Maker Faire Brno (1. den)"
    assert meetup1["location"] == "Brněnské výstaviště, Brno"
    assert meetup1["url"] == "https://makerfaire.cz/brno/"
    assert meetup1["source_url"] == "https://makerfaire.cz/brno/"
    assert meetup1["series_name"] == "Maker Faire"
    assert meetup1["series_org"] == "komunita technologických kutilů"
    assert meetup1["series_url"] == "https://makerfaire.cz/"
    assert meetup1["starts_at"] == datetime(
        2026, 10, 17, 0, 0, tzinfo=ZoneInfo("Europe/Prague")
    )
    assert meetup1["ends_at"] is None

    # Check second day
    meetup2 = meetups[1]
    assert meetup2["title"] == "Maker Faire Brno (2. den)"
    assert meetup2["location"] == "Brněnské výstaviště, Brno"
    assert meetup2["starts_at"] == datetime(
        2026, 10, 18, 0, 0, tzinfo=ZoneInfo("Europe/Prague")
    )


def test_parse_single_day_event():
    """Test parsing detail page with single-day event without time (Rychnov nad Kněžnou)."""
    response = HtmlResponse(
        "https://makerfaire.cz/rychnov-nad-kneznou/",
        body=Path(FIXTURES_DIR / "detail.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    assert len(meetups) == 1

    meetup = meetups[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Rychnov nad Kněžnou"
    assert meetup["location"] == "Zámecká jízdárna, Rychnov nad Kněžnou"
    assert meetup["url"] == "https://makerfaire.cz/rychnov-nad-kneznou/"
    assert meetup["source_url"] == "https://makerfaire.cz/rychnov-nad-kneznou/"
    assert meetup["starts_at"] == datetime(
        2026, 4, 19, 0, 0, tzinfo=ZoneInfo("Europe/Prague")
    )
    assert meetup["ends_at"] is None


def test_parse_single_day_with_time():
    """Test parsing detail page with single-day event with time (Ostrava)."""
    response = HtmlResponse(
        "https://makerfaire.cz/ostrava/",
        body=Path(FIXTURES_DIR / "detail-time.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    assert len(meetups) == 1

    meetup = meetups[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Ostrava"
    assert meetup["location"] == "Trojhalí Karolina, Ostrava"
    assert meetup["url"] == "https://makerfaire.cz/ostrava/"
    assert meetup["source_url"] == "https://makerfaire.cz/ostrava/"
    assert meetup["starts_at"] == datetime(
        2026, 5, 23, 10, 0, tzinfo=ZoneInfo("Europe/Prague")
    )
    assert meetup["ends_at"] == datetime(
        2026, 5, 23, 17, 0, tzinfo=ZoneInfo("Europe/Prague")
    )


def test_parse_something_that_looks_like_time_but_isnt():
    response = HtmlResponse(
        "https://makerfaire.cz/mlada-boleslav/",
        body=Path(FIXTURES_DIR / "detail-not-time.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    assert len(meetups) == 1

    meetup = meetups[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire Mladá Boleslav"
    assert meetup["location"] == "Pluhárna, Mladá Boleslav"
    assert meetup["url"] == "https://makerfaire.cz/mlada-boleslav/"
    assert meetup["source_url"] == "https://makerfaire.cz/mlada-boleslav/"
    assert meetup["starts_at"] == datetime(
        2026, 9, 19, 0, 0, tzinfo=ZoneInfo("Europe/Prague")
    )
    assert meetup["ends_at"] is None


def test_parse_complicated_location():
    response = HtmlResponse(
        "https://makerfaire.cz/ceske-budejovice/",
        body=Path(FIXTURES_DIR / "detail-location.html").read_bytes(),
    )
    meetups = list(Spider().parse_city(response))

    assert len(meetups) == 1

    meetup = meetups[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Maker Faire České Budějovice"
    assert (
        meetup["location"]
        == "Národní pavilon Z – Výstaviště České Budějovice, České Budějovice"
    )
    assert meetup["url"] == "https://makerfaire.cz/ceske-budejovice/"
    assert meetup["source_url"] == "https://makerfaire.cz/ceske-budejovice/"
    assert meetup["starts_at"] == datetime(
        2026, 9, 3, 0, 0, tzinfo=ZoneInfo("Europe/Prague")
    )
    assert meetup["ends_at"] is None


def test_parse_time_with_em_dash():
    """Test parse_time with em dash (—)."""
    spider = Spider()
    start, end = spider.parse_time("10:00—17:00")

    assert start == time(10, 0)
    assert end == time(17, 0)


def test_parse_time_with_en_dash():
    """Test parse_time with en dash (–)."""
    spider = Spider()
    start, end = spider.parse_time("10:00–17:00")

    assert start == time(10, 0)
    assert end == time(17, 0)


def test_parse_time_with_hyphen():
    """Test parse_time with regular hyphen (-)."""
    spider = Spider()
    start, end = spider.parse_time("10:00-17:00")

    assert start == time(10, 0)
    assert end == time(17, 0)


def test_parse_time_with_spaces():
    """Test parse_time with spaces around dash."""
    spider = Spider()
    start, end = spider.parse_time("10:00 – 17:00")
    assert start == time(10, 0)
    assert end == time(17, 0)


def test_parse_time_without_spaces():
    """Test parse_time without spaces around dash."""
    spider = Spider()
    start, end = spider.parse_time("10:00–17:00")

    assert start == time(10, 0)
    assert end == time(17, 0)


def test_parse_time_with_none():
    """Test parse_time with None input."""
    spider = Spider()
    start, end = spider.parse_time(None)

    assert start is None
    assert end is None


def test_parse_time_invalid():
    """Test parse_time with invalid input raises ValueError."""
    spider = Spider()

    with pytest.raises(ValueError, match="Could not parse time"):
        spider.parse_time("invalid time format")
