from datetime import date
from decimal import Decimal
from textwrap import dedent

import pytest

from juniorguru_plucker.exchange_rates.spider import (
    get_last_monday,
    parse_exchange_rate,
    parse_lines,
)


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Izrael|nový šekel|1|ILS|6,179", dict(code="ILS", rate=Decimal("6.179"))),
        ("USA|dolar|1|USD|22,030", dict(code="USD", rate=Decimal("22.030"))),
        ("EMU|euro|1|EUR|23,735", dict(code="EUR", rate=Decimal("23.735"))),
    ],
)
def test_parse_exchange_rate(line, expected):
    assert parse_exchange_rate(line) == expected


@pytest.mark.parametrize(
    "date, expected",
    [
        pytest.param(date(2023, 4, 12), date(2023, 4, 10), id="Wednesday"),
        pytest.param(date(2023, 4, 10), date(2023, 4, 10), id="Monday"),
        pytest.param(date(2023, 4, 16), date(2023, 4, 10), id="Sunday"),
    ],
)
def test_get_last_monday(date, expected):
    assert get_last_monday(date) == expected


def test_parse_lines():
    assert parse_lines(
        dedent(
            """
                27.03.2023 #61
                země|měna|množství|kód|kurz
                Austrálie|dolar|1|AUD|14,648
                Velká Británie|libra|1|GBP|27,030
            """
        )
    ) == [
        "Austrálie|dolar|1|AUD|14,648",
        "Velká Británie|libra|1|GBP|27,030",
    ]
