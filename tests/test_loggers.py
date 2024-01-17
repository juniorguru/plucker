import pytest
from scrapy.settings import Settings

from juniorguru_plucker.loggers import get_logging_level


@pytest.mark.parametrize(
    "settings, argv, expected",
    [
        pytest.param({}, [], "DEBUG", id="default from Scrapy"),
        ({"LOG_LEVEL": "DEBUG"}, [], "DEBUG"),
        ({"LOG_LEVEL": "DEBUG"}, ["--debug"], "DEBUG"),
        ({"LOG_LEVEL": "DEBUG"}, ["-d"], "DEBUG"),
        ({"LOG_LEVEL": "INFO"}, [], "INFO"),
        ({"LOG_LEVEL": "INFO"}, ["--debug"], "DEBUG"),
        ({"LOG_LEVEL": "INFO"}, ["-d"], "DEBUG"),
        ({"LOG_LEVEL": "WARNING"}, [], "WARNING"),
    ],
)
def test_get_logging_level(settings: dict, argv: list[str], expected: str):
    assert get_logging_level(Settings(settings), argv) == expected
