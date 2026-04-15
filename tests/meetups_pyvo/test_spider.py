from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from scrapy.http import TextResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_pyvo.spider import Spider


TODAY = date(2026, 4, 15)


@pytest.fixture()
def response() -> TextResponse:
    return TextResponse(
        "https://pyvo.cz/api/pyvo.ics",
        body=(Path(__file__).parent / "pyvo.ics").read_bytes(),
    )


def test_parse_returns_confirmed_future_events(response: TextResponse):
    meetups = list(Spider().parse(response, today=TODAY))

    assert len(meetups) == 1
    assert meetups[0]["title"] == "Pražské Pyvo #179 Úvodní představení Spark a PySpark"


def test_parse_filters_past_events(response: TextResponse):
    meetups = list(Spider().parse(response, today=TODAY))

    titles = [meetup["title"] for meetup in meetups]
    assert "Ostravské Pyvo – Dubnový pokec (AI agenti)" not in titles


def test_parse_filters_tentative_events(response: TextResponse):
    meetups = list(Spider().parse(response, today=TODAY))

    titles = [meetup["title"] for meetup in meetups]
    assert not any("nepotvrzeno" in title for title in titles)


def test_parse_event_fields(response: TextResponse):
    meetup = list(Spider().parse(response, today=TODAY))[0]

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "Pražské Pyvo #179 Úvodní představení Spark a PySpark"
    assert meetup["url"] == "https://pyvo.cz/praha-pyvo/2026-04/"
    assert meetup["source_url"] == "https://pyvo.cz/api/pyvo.ics"
    assert meetup["series_name"] == "Pyvo"
    assert meetup["series_org"] == "komunita kolem Pythonu"
    assert meetup["series_url"] == "https://pyvo.cz/"
    assert meetup["starts_at"] == datetime(2026, 4, 15, 16, 30, tzinfo=timezone.utc)
    assert meetup["ends_at"] == datetime(
        2026, 4, 15, 16, 30, tzinfo=timezone.utc
    ) + timedelta(hours=3)
    assert "Na Věnečku" in meetup["location"]
    assert meetup["description"] is not None
