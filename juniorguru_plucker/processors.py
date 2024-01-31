import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping


def absolute_url(url: str, loader_context: Mapping):
    return loader_context["response"].urljoin(url)


def split(string: str, by: str = ",") -> list[str]:
    if string:
        return list(filter(None, map(str.strip, string.split(by))))
    return []


def first(iterable: Iterable[Any]) -> Any | None:
    for item in iterable:
        if item is not None:
            return item
    return None


def last(iterable: Iterable[Any]) -> Any | None:
    return first(reversed(list(iterable)))


def parse_relative_date(text, today=None) -> date:
    today = today or date.today()
    if "week" in text or "týdn" in text:
        if match := re.search(r"\d+", text):
            weeks_ago = int(match.group(0))
            return today - timedelta(weeks=weeks_ago)
        raise ValueError(text)
    if "minute" in text or "hour" in text or "minut" in text or "hod" in text:
        return today
    if "today" in text or "dnes" in text:
        return today
    if "yesterday" in text or "včera" in text:
        return today - timedelta(days=1)
    if "day" in text or "dny" in text or "dnem" in text:
        if match := re.search(r"\d+", text):
            days_ago = int(match.group(0))
            return today - timedelta(days=days_ago)
        raise ValueError(text)
    if "month" in text or "měs" in text:
        if match := re.search(r"\d+", text):
            months_ago = int(match.group(0))
            return today - timedelta(days=months_ago * 30)
        raise ValueError(text)
    if "year" in text or "rok" in text or "let" in text:
        if match := re.search(r"\d+", text):
            years_ago = int(match.group(0))
            return today - timedelta(days=years_ago * 365)
    if "now" in text or "teď" in text or "nyní" in text:
        return today
    raise ValueError(text)


def parse_iso_date(text: str) -> date:
    return datetime.fromisoformat(text).date()
