from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from scrapy.http import TextResponse

from jg.plucker.items import Meetup
from jg.plucker.meetups_nepyvo.spider import Spider, get_event_url


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
    meetup = next(iter(Spider().parse(response, today=TODAY)))

    assert isinstance(meetup, Meetup)
    assert meetup["title"] == "AI mění (nejen) svět IT"
    assert meetup["url"] == "https://nepyvo.cz/#69cb8efbdc8b45d48bcd7791@nepyvo.cz"
    assert meetup["source_url"] == "https://nepyvo.cz/api/calendar/nepyvo.ics"
    assert meetup["series_name"] == "NePyvo"
    assert meetup["series_org"] == "komunita kolem Pythonu"
    assert meetup["series_url"] == "https://nepyvo.cz/"
    assert meetup["starts_at"] == datetime(2026, 4, 16, 17, 0, tzinfo=UTC)
    assert meetup["ends_at"] == datetime(2026, 4, 16, 20, 0, tzinfo=UTC)
    assert "Hostinec Pod Schody" in meetup["location"]
    assert meetup["description"] is not None


def test_parse_events_have_unique_urls(response: TextResponse):
    meetups = list(Spider().parse(response, today=date(2026, 1, 1)))
    urls = [meetup["url"] for meetup in meetups]

    assert len(meetups) == 2
    assert len(set(urls)) == len(urls)


def test_get_event_url_prefers_event_url():
    assert (
        get_event_url("https://example.com/event", "abc@nepyvo.cz")
        == "https://example.com/event"
    )


def test_get_event_url_uses_uid():
    assert get_event_url(None, "abc@nepyvo.cz") == "https://nepyvo.cz/#abc@nepyvo.cz"


@pytest.mark.parametrize("uid", [None, ""])
def test_get_event_url_raises_without_uid(uid: str | None):
    with pytest.raises(ValueError):
        get_event_url(None, uid)
