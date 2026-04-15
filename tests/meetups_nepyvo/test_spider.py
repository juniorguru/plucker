from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from scrapy.http import TextResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_nepyvo.spider import Spider


TODAY = date(2026, 4, 15)


@pytest.fixture()
def response() -> TextResponse:
    return TextResponse(
        "https://nepyvo.cz/api/calendar/nepyvo.ics",
        body=(Path(__file__).parent / "nepyvo.ics").read_bytes(),
    )


def test_parse_returns_future_events(response: TextResponse):
    meetups = list(Spider().parse(response, today=TODAY))

    assert len(meetups) == 1
    assert meetups[0]["title"] == "AI mění (nejen) svět IT"


def test_parse_filters_past_events(response: TextResponse):
    meetups = list(Spider().parse(response, today=TODAY))

    titles = [meetup["title"] for meetup in meetups]
    assert "NePyvo 2.0" not in titles


def test_parse_event_fields(response: TextResponse):
    meetup = list(Spider().parse(response, today=TODAY))[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "AI mění (nejen) svět IT"
    assert meetup["url"] == "https://nepyvo.cz/"
    assert meetup["source_url"] == "https://nepyvo.cz/api/calendar/nepyvo.ics"
    assert meetup["series_name"] == "NePyvo"
    assert meetup["series_org"] == "komunita kolem Pythonu"
    assert meetup["series_url"] == "https://nepyvo.cz/"
    assert meetup["starts_at"] == datetime(2026, 4, 16, 17, 0, tzinfo=timezone.utc)
    assert meetup["ends_at"] == datetime(2026, 4, 16, 20, 0, tzinfo=timezone.utc)
    assert "Hostinec Pod Schody" in meetup["location"]
    assert meetup["description"] is not None
